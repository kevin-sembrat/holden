# Routing Protocol Troubleshooting Basics

When a route that is expected to exist is missing from the routing
table, the first question is always whether the underlying neighbor
relationship is up at all -- a routing protocol cannot install routes
learned from a neighbor it has not formed an adjacency with, regardless
of how correct the rest of the configuration looks. Checking neighbor or
adjacency state should always come before inspecting route filters,
metrics, or redistribution policy.

A neighbor relationship failing to form is most often caused by one of a
small number of things: a mismatch in a required parameter that the
protocol insists must match on both sides (such as area ID for OSPF,
autonomous system number for BGP, or hello/dead timer values), an access
list or firewall rule blocking the protocol's control-plane traffic, or a
layer 1/2 problem on the link itself that also happens to be masking a
routing issue. Because control-plane traffic is often low-volume, a
marginal physical link can pass routing protocol hellos intermittently
while looking otherwise fine, producing a neighbor relationship that
flaps rather than one that simply fails outright.

Once a neighbor relationship is confirmed stable, and a route is still
missing, the next most common cause is redistribution or filtering: a
route learned correctly by one protocol may be deliberately withheld from
being offered to another protocol, or filtered on ingress or egress by an
explicit route-map or distribute-list. It is also worth checking for a
better route to the same destination arriving from a different, more
locally preferred source (a lower administrative distance from a
different protocol, or a more specific matching prefix), since only the
best route per prefix is normally installed in the forwarding table even
when multiple valid paths exist.

Route flapping -- a route repeatedly appearing and disappearing -- almost
always traces back to an unstable link or an unstable neighbor
relationship somewhere upstream, not to the routing protocol
configuration itself, and the underlying instability should be resolved
before applying route dampening or similar suppression as a workaround.
