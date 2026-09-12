# VLAN Configuration Fundamentals

A VLAN (Virtual LAN) partitions a single physical switch, or a set of
switches, into multiple logically separate broadcast domains. Every
access port on a switch is assigned to exactly one VLAN, and traffic
entering that port is treated as belonging to that VLAN's broadcast
domain regardless of the physical topology. Trunk ports, by contrast,
carry traffic for multiple VLANs simultaneously by tagging each frame
with an 802.1Q VLAN identifier as it crosses the trunk link.

The single most common VLAN misconfiguration is a mismatch between the
VLAN assigned to an access port and the VLAN the attached device actually
expects to be on. This typically shows up as a device that has a link
light and appears to have a valid physical connection, but cannot obtain
a DHCP lease or reach expected resources, because its broadcast traffic
is being delivered into the wrong domain entirely. Comparing the
running VLAN assignment on the port against the documented or expected
assignment for that physical location is usually the fastest way to
confirm this class of problem.

A second common class of issue is a native VLAN mismatch on a trunk:
each end of an 802.1Q trunk has a native VLAN, used for untagged traffic,
and if the two ends disagree on which VLAN is native, untagged traffic
gets misdelivered on one side of the link while every other VLAN
continues to trunk normally. This can be subtle because most traffic on
the trunk keeps working, and only devices relying on the native VLAN
specifically are affected.

Finally, a VLAN must exist in the switch's VLAN database before it can be
assigned to a port; assigning a port to a VLAN number that has not been
created will typically leave the port in an inactive or non-forwarding
state for that VLAN even though the assignment itself was accepted.
