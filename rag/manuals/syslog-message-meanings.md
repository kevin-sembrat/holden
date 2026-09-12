# Common Syslog Message Meanings

Device syslog output follows a consistent severity scale from 0
(emergency) through 7 (debugging), and the severity level is usually the
single most useful field for triage before even reading the message text
-- a stream of severity-6 (informational) messages about routine state
changes is normal operational noise, while a severity-2 (critical) or
lower message warrants immediate attention regardless of how familiar the
message text looks.

Link state change messages (an interface transitioning to up or down)
are typically severity 3 or 5 depending on platform and are expected
during planned maintenance, cabling work, or a device reboot. The same
message appearing repeatedly for the same interface outside of any
planned activity is a strong signal of the intermittent physical-layer
problems described in the interface error counters material -- a flapping
link produces exactly this pattern.

Configuration change messages record who made a change and from where,
and are foundational to audit trails: any config change message that
does not correspond to a known, authorized change should be treated as a
potential incident until it is explained, not dismissed as noise.

Authentication failure messages, particularly repeated failures against
the same account or from the same source in a short window, should be
correlated with legitimate change activity before being dismissed --
a burst of failures immediately followed by a successful login and a
config change is a very different situation from a burst of failures
with no successful login at all.

Environmental messages (temperature, power supply, fan status) are
often the earliest warning of impending hardware failure and are
frequently under-prioritized relative to their severity level, because
degraded-but-still-functioning hardware often only logs at a moderate
severity right up until the point of an actual outage.
