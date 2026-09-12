# Spanning Tree Protocol Issues

Spanning Tree Protocol exists to prevent loops in a switched network that
has redundant physical paths, by electing a single root bridge and then
placing every other port into exactly one of a small number of states:
blocking, listening, learning, or forwarding. Only a port in the
forwarding state actually passes user traffic; the other states exist to
let the topology converge safely before traffic flows, which is also why
STP convergence after a topology change is not instantaneous.

The most damaging class of STP problem is a loop that forms despite STP
being enabled, and this is almost always caused by something that
prevents STP's own control traffic (BPDUs) from being exchanged
correctly on a link that should be participating in the topology. A port
configured with BPDU filtering or BPDU guard misapplied to a link that
is not actually an edge port is a common cause: the port either stops
sending/receiving the BPDUs needed to detect the redundant path, or gets
disabled in a way that looks like a straightforward port-down event
rather than an STP misconfiguration, which can send troubleshooting in
the wrong direction entirely.

Frequent topology change notifications (TCNs) are themselves a symptom
worth investigating rather than ignoring: each TCN causes switches to
age out their MAC address tables faster than normal to keep forwarding
correct during reconvergence, and a network with a flapping port or an
unstable link will generate a steady stream of TCNs that degrades normal
forwarding performance even when no actual loop is present. A port that
is flapping between forwarding and blocking, or repeatedly resetting to
listening/learning, is a strong indicator of exactly this kind of
instability upstream.

Portfast is intended only for ports connecting to a single end host that
will never itself run STP or introduce a loop; enabling it on a port that
connects to another switch (even accidentally, such as a temporary lab
cable or an unmanaged switch plugged in by an end user) removes the
delay STP normally uses to safely detect a loop on that port, and is one
of the most common root causes of an accidental loop in an otherwise
correctly configured network.
