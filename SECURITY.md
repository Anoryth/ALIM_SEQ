# Security policy

## ⚠️ Safety warning (please read)

ALIM_SEQ drives **power supplies** on real hardware. Its protections — thermal
cut-off, orderly shutdowns, emergency stop — are **software**. They **do not
replace** a **hardware** safety device (interlock, fuse, limiter) nor the operator's
judgement.

The software is provided **without any warranty** (GNU GPL-3.0 license), is **not
certified** for critical use, and is used **at your own risk**. Always check the safe
operating area (SOA), the wiring and the voltage rating of your setup.

**Network.** The SCPI/TCPIP protocol has **no authentication**: any host on the
network can drive the instruments. Connect the hardware on an **isolated bench
network** (VLAN or dedicated segment), never exposed to the office network or the
Internet.

## Supported versions

Only the **latest** released version receives fixes.

| Version | Supported |
|---|---|
| latest (`main`) | ✅ |
| earlier | ❌ |

## Reporting a vulnerability

Please **do not** open a public issue for a security flaw.

Use the **"Report a vulnerability"** feature (*Security* tab → *Advisories*) of the
GitHub repository, which opens a **private** channel with the maintainers. Describe:

- the affected component and version,
- the reproduction steps,
- the potential impact (hardware safety, code execution, information leak).

A response is targeted within **a few business days**. Please allow a reasonable time
to fix before any public disclosure.
