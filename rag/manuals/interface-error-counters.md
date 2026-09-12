# Interface Error Counters and CRC Errors

Every physical interface maintains a set of running counters that reflect
the health of the link at layer 1 and layer 2. The most commonly
referenced counters are input errors, CRC errors, frame errors, runts,
and giants. A steadily climbing CRC error count almost always points to a
physical-layer problem rather than a configuration problem: a damaged or
out-of-spec cable, a dirty or failing transceiver, a duplex mismatch
between the two ends of a link, or electrical interference along the
cable run.

Duplex mismatches deserve special attention because they produce a
distinctive signature: one side of the link reports late collisions and
the other side reports CRC and frame errors, while both sides otherwise
show the link as up. This happens when one end is fixed at full duplex
and the other end is either fixed at half duplex or left on auto-negotiate
and falls back to half duplex because the far end never advertised
capabilities. The fix is to match duplex settings explicitly on both ends,
or to set both ends to auto-negotiate and confirm they actually agree
after the change.

Runts (frames shorter than the minimum 64 bytes) and giants (frames
longer than the maximum allowed for the configured MTU) are usually a
sign of a misbehaving NIC on an attached device, or of a jabbering device
that never properly ends a transmission. A small, non-increasing count of
either is not typically actionable; a count that increases every time the
interface is polled indicates an active problem on the segment.

As a general troubleshooting order: check for a rapidly increasing error
count first, then check duplex/speed settings on both ends, then inspect
or replace the physical cable and transceiver, and only after ruling out
the physical layer should the investigation move up to switching or
routing configuration on that interface.
