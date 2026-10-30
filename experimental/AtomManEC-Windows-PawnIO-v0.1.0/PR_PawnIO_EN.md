# Draft PR: AtomManEC — restricted EC fan RPM reader for Minisforum AtomMan X7 Ti

**Status:** draft for maintainer review; no hardware execution from PawnIO validated.

The AtomMan X7 Ti (vendor `Micro Computer (HK) Tech Limited`, product `AtomMan X Series`, board `MTBAC`) exposes a CPU fan tachometer through vendor EC command `0xD5` with low/high offsets `0x18/0x19`. The Linux in-tree-independent driver uses ACPI method `\\_SB.PC00.LPCB.H_EC.EC2R`, and has measured plausible dynamic fan RPM on this model. AIDA64 on Windows also reports fan RPM around 1900–2200 while Secure Boot/VBS/HVCI are enabled.

`AtomManEC.p` is a deliberately narrow PawnIO module, intended for the official signed-module pipeline, that:

- issues only the two required vendor EC reads using command/status `0x6C` and data `0x68`;
- exposes only `ioctl_read_fan_rpm` (no general port reads/writes, no fan control);
- enforces bounded IBF/OBF waits and rejects RPM >= 4000;
- leaves Windows Secure Boot and HVCI untouched.

**Request for maintainer feedback before acceptance:**

1. Whether direct 0x6C/0x68 transactions safely coexist with the Windows ACPI EC driver. The Linux code invokes firmware's ACPI method rather than using raw ports. The PawnIO prototype cannot guarantee firmware arbitration.
2. Which synchronization primitive/mutant should be held for this nonstandard vendor EC pair; the user-mode example should acquire it for the full transaction if appropriate.
3. Whether board identity should be validated in-module using an available SMBIOS native; the Python proof of concept validates DMI, but third-party PawnIO callers could bypass that guard.
4. Review status timing and `microsleep2` bounded stalls (20 us x 500 retries per stage) before any hardware test.
5. Pawn syntax/warning-free compilation in official CI has not yet been verified.

**Source and design links:**
- https://github.com/sysadmin-info/AtomMan/tree/main/drivers/atomman-ec-fan
- https://github.com/namazso/PawnIO.Modules/blob/main/LpcACPIEC.p
- https://github.com/Gitii/ms-a1-fan-controller

No unsigned driver/test-signing bypass is requested. We need a reviewed official signed module release for use on locked-down Windows 11.
