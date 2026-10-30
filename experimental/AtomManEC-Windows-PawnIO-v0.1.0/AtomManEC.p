// SPDX-License-Identifier: LGPL-2.1-or-later
// AtomMan X7 Ti fan RPM reader for PawnIO.
//
// EXPERIMENTAL, source only. No signed .bin is distributed.
// The module submits ONLY the documented D5 read transaction for 0x18/0x19
// to the vendor EC I/O pair 0x6C (command/status), 0x68 (data).
// IMPORTANT: EC read transactions still WRITE command/offset bytes to ports;
// 'read-only' describes the requested EC operation, not the I/O bus.
//
// Reference: AtomMan Linux driver atomman_ec_fan.c; Minisforum 6C EC
// implementation described in Gitii/ms-a1-fan-controller.

#include <pawnio.inc>

const EC_CMD_PORT = 0x6C;
const EC_DATA_PORT = 0x68;
const EC_READ_COMMAND = 0xD5;
const EC_LOW_RPM = 0x18;
const EC_HIGH_RPM = 0x19;
const EC_STATUS_OBF = 0x01;
const EC_STATUS_IBF = 0x02;
const EC_WAIT_TRIES = 500;
const EC_WAIT_US = 20;
const EC_MAX_RPM = 4000;

// Poll at most 10 ms (500 x 20 us) per transfer phase.
// No unbounded waits, register scanning, arbitrary writes or fan-control API.
NTSTATUS:ec_wait(mask, expected) {
    for (new i = 0; i < EC_WAIT_TRIES; i++) {
        new status = io_in_byte(EC_CMD_PORT);
        if ((status & mask) == expected)
            return STATUS_SUCCESS;
        microsleep2(EC_WAIT_US);
    }
    return STATUS_IO_TIMEOUT;
}

NTSTATUS:ec_read_byte(address, &value) {
    new NTSTATUS:status = ec_wait(EC_STATUS_IBF, 0);
    if (!NT_SUCCESS(status))
        return status;

    io_out_byte(EC_CMD_PORT, EC_READ_COMMAND);

    status = ec_wait(EC_STATUS_IBF, 0);
    if (!NT_SUCCESS(status))
        return status;

    io_out_byte(EC_DATA_PORT, address);

    status = ec_wait(EC_STATUS_OBF, EC_STATUS_OBF);
    if (!NT_SUCCESS(status))
        return status;

    value = io_in_byte(EC_DATA_PORT) & 0xFF;
    return STATUS_SUCCESS;
}

/// Read AtomMan X Series / MTBAC CPU fan RPM (experimental).
///
/// @param in Unused
/// @param in_size Must be 0
/// @param out [0] = RPM (16-bit little-endian, 0..3999)
/// @param out_size Must be 1
/// @return NTSTATUS (STATUS_SUCCESS, STATUS_IO_TIMEOUT or STATUS_UNSUCCESSFUL)
/// @warning Do not call concurrently with AIDA64 or another EC reader.
/// @warning Caller must verify DMI identity and coordinate EC ownership.
/// @warning The EC command and offset writes are part of a *read* transaction.
DEFINE_IOCTL_SIZED(ioctl_read_fan_rpm, 0, 1) {
    new low;
    new high;
    new NTSTATUS:status = ec_read_byte(EC_LOW_RPM, low);
    if (!NT_SUCCESS(status))
        return status;

    status = ec_read_byte(EC_HIGH_RPM, high);
    if (!NT_SUCCESS(status))
        return status;

    new rpm = ((high & 0xFF) << 8) | (low & 0xFF);
    if (rpm >= EC_MAX_RPM)
        return STATUS_UNSUCCESSFUL;

    out[0] = rpm;
    return STATUS_SUCCESS;
}

NTSTATUS:main() {
    return STATUS_SUCCESS;
}
