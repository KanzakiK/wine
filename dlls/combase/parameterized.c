/* WinRT parameterized interface identifiers.
 *
 * This library is free software; you can redistribute it and/or modify it
 * under the terms of the GNU Lesser General Public License as published by
 * the Free Software Foundation; either version 2.1 of the License, or
 * (at your option) any later version.
 */
#define COBJMACROS
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "objbase.h"
#include "roparameterizediid.h"
#include "bcrypt.h"

/* Signatures and UUIDv5 namespace are specified by the WinRT type system.
 * Resolve through the caller's metadata locator, not a list of known classes. */
struct signature
{
    char *text;
    size_t len;
    HRESULT hr;
    unsigned int depth;
    const IRoMetaDataLocator *locator;
};

struct metadata_builder
{
    IRoSimpleMetaDataBuilder iface;
    struct signature *signature;
    UINT32 count, position, arguments;
    const WCHAR **names;
    BOOL called;
};

static void append(struct signature *s, const char *text)
{
    size_t len = strlen(text);
    char *new_text;
    if (FAILED(s->hr)) return;
    if (len > ~(size_t)0 - s->len - 1 || !(new_text = realloc(s->text, s->len + len + 1)))
    {
        s->hr = E_OUTOFMEMORY;
        return;
    }
    s->text = new_text;
    memcpy(s->text + s->len, text, len + 1);
    s->len += len;
}

static void append_name(struct signature *s, const WCHAR *name)
{
    int len;
    char *utf8;
    if (FAILED(s->hr)) return;
    if (!name) { s->hr = E_INVALIDARG; return; }
    len = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, name, -1, NULL, 0, NULL, NULL);
    if (!len) { s->hr = E_INVALIDARG; return; }
    if (!(utf8 = malloc(len))) { s->hr = E_OUTOFMEMORY; return; }
    WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, name, -1, utf8, len, NULL, NULL);
    append(s, utf8);
    free(utf8);
}

static void append_guid(struct signature *s, const GUID *id)
{
    char text[39];
    snprintf(text, sizeof(text), "{%08lx-%04x-%04x-%02x%02x-%02x%02x%02x%02x%02x%02x}",
             id->Data1, id->Data2, id->Data3, id->Data4[0], id->Data4[1], id->Data4[2],
             id->Data4[3], id->Data4[4], id->Data4[5], id->Data4[6], id->Data4[7]);
    append(s, text);
}

static void type_signature(struct signature *, UINT32, const WCHAR **, UINT32 *);

static struct metadata_builder *begin(IRoSimpleMetaDataBuilder *iface)
{
    struct metadata_builder *b = (struct metadata_builder *)iface;
    if (b->called) b->signature->hr = E_INVALIDARG;
    b->called = TRUE;
    return b;
}

static HRESULT WINAPI set_interface(IRoSimpleMetaDataBuilder *iface, GUID id)
{
    struct signature *s = begin(iface)->signature;
    append_guid(s, &id);
    return s->hr;
}

static HRESULT WINAPI set_delegate(IRoSimpleMetaDataBuilder *iface, GUID id)
{
    struct signature *s = begin(iface)->signature;
    append(s, "delegate("); append_guid(s, &id); append(s, ")");
    return s->hr;
}

static HRESULT set_default(IRoSimpleMetaDataBuilder *iface, const char *kind, const WCHAR *name,
                           UINT32 count, const WCHAR **names, const GUID *id)
{
    struct signature *s = begin(iface)->signature;
    UINT32 position = 0;
    append(s, kind); append_name(s, name); append(s, ";");
    if (id) append_guid(s, id);
    else
    {
        type_signature(s, count, names, &position);
        if (position != count && SUCCEEDED(s->hr)) s->hr = E_INVALIDARG;
    }
    append(s, ")");
    return s->hr;
}

static HRESULT WINAPI set_group(IRoSimpleMetaDataBuilder *i, const WCHAR *n, const WCHAR *d, const GUID *id)
{ return set_default(i, "ig(", n, 1, &d, id); }
static HRESULT WINAPI set_group_generic(IRoSimpleMetaDataBuilder *i, const WCHAR *n, UINT32 c, const WCHAR **d)
{ return set_default(i, "ig(", n, c, d, NULL); }
static HRESULT WINAPI set_class(IRoSimpleMetaDataBuilder *i, const WCHAR *n, const WCHAR *d, const GUID *id)
{ return set_default(i, "rc(", n, 1, &d, id); }
static HRESULT WINAPI set_class_generic(IRoSimpleMetaDataBuilder *i, const WCHAR *n, UINT32 c, const WCHAR **d)
{ return set_default(i, "rc(", n, c, d, NULL); }

static HRESULT WINAPI set_struct(IRoSimpleMetaDataBuilder *iface, const WCHAR *name, UINT32 count, const WCHAR **fields)
{
    struct signature *s = begin(iface)->signature;
    UINT32 i, position;
    append(s, "struct("); append_name(s, name);
    if (count && !fields) s->hr = E_INVALIDARG;
    for (i = 0; i < count && SUCCEEDED(s->hr); ++i)
    {
        append(s, ";"); position = 0;
        type_signature(s, 1, &fields[i], &position);
    }
    append(s, ")");
    return s->hr;
}

static HRESULT WINAPI set_enum(IRoSimpleMetaDataBuilder *iface, const WCHAR *name, const WCHAR *base)
{
    struct signature *s = begin(iface)->signature;
    append(s, "enum("); append_name(s, name); append(s, ";");
    if (base && !wcscmp(base, L"Int32")) append(s, "i4");
    else if (base && !wcscmp(base, L"UInt32")) append(s, "u4");
    else s->hr = E_INVALIDARG;
    append(s, ")");
    return s->hr;
}

static HRESULT WINAPI set_parameterized(IRoSimpleMetaDataBuilder *iface, GUID id, UINT32 count)
{
    struct metadata_builder *b = begin(iface);
    struct signature *s = b->signature;
    UINT32 i;
    if (!count || count > b->count - b->position) return s->hr = E_INVALIDARG;
    b->arguments = count;
    append(s, "pinterface("); append_guid(s, &id);
    for (i = 0; i < count && SUCCEEDED(s->hr); ++i)
    {
        append(s, ";");
        type_signature(s, b->count, b->names, &b->position);
    }
    append(s, ")");
    return s->hr;
}

static const IRoSimpleMetaDataBuilderVtbl builder_vtbl =
{
    set_interface, set_delegate, set_group, set_group_generic, set_class, set_class_generic,
    set_struct, set_enum, set_parameterized, set_parameterized
};

static void type_signature(struct signature *s, UINT32 count, const WCHAR **names, UINT32 *position)
{
    static const struct { const WCHAR *name; const char *signature; } primitives[] =
    {
        {L"UInt8", "u1"}, {L"Int16", "i2"}, {L"UInt16", "u2"}, {L"Int32", "i4"},
        {L"UInt32", "u4"}, {L"Int64", "i8"}, {L"UInt64", "u8"}, {L"Single", "f4"},
        {L"Double", "f8"}, {L"Boolean", "b1"}, {L"Char16", "c2"}, {L"String", "string"},
        {L"Guid", "g16"}, {L"Object", "cinterface(IInspectable)"}
    };
    struct metadata_builder b = {{&builder_vtbl}, s, count, 0, 0, names, FALSE};
    const WCHAR *name;
    HRESULT hr;
    unsigned int i;
    if (FAILED(s->hr)) return;
    if (!names || *position >= count || !(name = names[(*position)++]) || s->depth >= 64)
    { s->hr = E_INVALIDARG; return; }
    for (i = 0; i < ARRAY_SIZE(primitives); ++i)
        if (!wcscmp(name, primitives[i].name)) { append(s, primitives[i].signature); return; }
    ++s->depth;
    b.position = *position;
    hr = IRoMetaDataLocator_Locate((IRoMetaDataLocator *)s->locator, name, &b.iface);
    if (FAILED(hr)) s->hr = hr;
    else if (!b.called) s->hr = E_INVALIDARG;
    *position = b.position;
    --s->depth;
}

HRESULT WINAPI RoGetParameterizedTypeInstanceIID(UINT32 count, const WCHAR **names,
        const IRoMetaDataLocator *locator, GUID *iid, ROPARAMIIDHANDLE *extra)
{
    static const UCHAR namespace[] = {0x11,0xf4,0x7a,0xd5,0x7b,0x73,0x42,0xc0,0xab,0xae,0x87,0x8b,0x1e,0x16,0xad,0xee};
    struct signature s = {NULL, 0, S_OK, 0, locator};
    BCRYPT_ALG_HANDLE alg = NULL;
    BCRYPT_HASH_HANDLE hash = NULL;
    UCHAR digest[20];
    UINT32 position = 0;
    NTSTATUS status;
    if (extra) *extra = NULL;
    if (!iid) return E_INVALIDARG;
    memset(iid, 0, sizeof(*iid));
    if (!locator || !names || count < 2) return E_INVALIDARG;
    type_signature(&s, count, names, &position);
    if (SUCCEEDED(s.hr) && (position != count || !s.text || strncmp(s.text, "pinterface(", 11))) s.hr = E_INVALIDARG;
    if (FAILED(s.hr)) goto done;
    status = BCryptOpenAlgorithmProvider(&alg, BCRYPT_SHA1_ALGORITHM, NULL, 0);
    if (!status) status = BCryptCreateHash(alg, &hash, NULL, 0, NULL, 0, 0);
    if (!status) status = BCryptHashData(hash, (UCHAR *)namespace, sizeof(namespace), 0);
    if (!status) status = BCryptHashData(hash, (UCHAR *)s.text, s.len, 0);
    if (!status) status = BCryptFinishHash(hash, digest, sizeof(digest), 0);
    if (hash) BCryptDestroyHash(hash);
    if (alg) BCryptCloseAlgorithmProvider(alg, 0);
    if (status) { s.hr = HRESULT_FROM_NT(status); goto done; }
    digest[6] = (digest[6] & 0x0f) | 0x50;
    digest[8] = (digest[8] & 0x3f) | 0x80;
    iid->Data1 = (DWORD)digest[0] << 24 | (DWORD)digest[1] << 16 | digest[2] << 8 | digest[3];
    iid->Data2 = digest[4] << 8 | digest[5];
    iid->Data3 = digest[6] << 8 | digest[7];
    memcpy(iid->Data4, digest + 8, 8);
    if (extra) { *extra = s.text; s.text = NULL; }
done:
    free(s.text);
    return s.hr;
}

void WINAPI RoFreeParameterizedTypeExtra(ROPARAMIIDHANDLE extra)
{
    free(extra);
}

const char * WINAPI RoParameterizedTypeExtraGetTypeSignature(ROPARAMIIDHANDLE extra)
{
    return extra;
}
