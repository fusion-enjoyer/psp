	.set noreorder

#include "pspstub.s"

/* USBHostFS: user-mode (0x4001) exports of usbhostfs.prx, see
   third_party/psplinkusb/usbhostfs/exports.exp. The prx is loaded at runtime,
   so these stubs are linked when the library registers. */
	STUB_START "USBHostFS",0x40090000,0x000A0005
	STUB_FUNC  0x75246D41,usbAsyncRegister
	STUB_FUNC  0x587DDEDA,usbAsyncUnregister
	STUB_FUNC  0xBA9F1145,usbAsyncRead
	STUB_FUNC  0xE4C00162,usbAsyncReadWithTimeout
	STUB_FUNC  0x5D1F19A0,usbAsyncWrite
	STUB_FUNC  0x89D91015,usbAsyncFlush
	STUB_FUNC  0xFF18E862,usbWaitForConnect
	STUB_FUNC  0x4ABA9C2B,usbWriteBulkData
	STUB_FUNC  0x642EF71E,usbLockBus
	STUB_FUNC  0x439E6C6C,usbUnlockBus
	STUB_END

/* KUBridge: provided by CFW SystemControl (ARK-4, PRO, LME). Lets a user-mode
   app load a kernel module such as usbhostfs.prx. */
	STUB_START "KUBridge",0x40090000,0x00010005
	STUB_FUNC  0x4C25EA72,kuKernelLoadModule
	STUB_END
