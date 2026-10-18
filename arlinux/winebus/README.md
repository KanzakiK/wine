# Android winebus backend

`dlls/winebus.sys/bus_arlinux.h` adapts the Winlator HID report mapping and
retains its LGPL-2.1-or-later notice. The Android branch in `bus_udev.c` includes
it directly; no source preparation patcher is required. ARLinux uses its same-UID
Unix-socket broker for physical and overlay controllers. PE and Unix driver halves
are compiled from the same source tree. The runtime carries the backend source,
this note and COPYING.LIB under share/arlinux/winebus.
