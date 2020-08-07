Notes for early adopters
========================

Though I am making an effort to ensure that the HTTP replicator is
reliable, I am not all that creative about thinking up ways that people
might like to configure things; for example, see below about my specific
concerns about --ip and --alias.  Just because a program is "bug-free"
with respect to a specification does not mean that the specification itself
is not buggy... so let me know if you find something to be misdesigned,
even if the code appears to be "working as intended".

I'd also like to improve the documentation of the replicator.  Please
point out places where the existing documentation is worded awkwardly or
confusingly, as well as anywhere that you find the documentation to just
be lacking.

Plus, of course, just general testing.  Use the replicator, monitor the
logs, and report any bugs you find.


The --ip option
---------------

I personally protect internal-only services on my network by having
them bind to an address which will not be routed (or NATed) outside my
local network (e.g., an IPv6 ULA from fc00::/7).  Or I run a service
bound to "localhost", and use a ssh tunnel to that machine with suitable
port forwarding.  Others apparently like to bind to the wildcard address
(0.0.0.0 or ::) and then filter based on the incoming peer's IP address.
I've added code intending to accommodate this latter approach, but as
it is not my style, I'm not sure I got it right.  I've also attempted
to document both approaches (and the approach of using firewall rules,
like nftables) in the "README-too.md" document.

Please let me know if either the code's behavior or the documentation
relating to the --ip option needs to be improved.


The --alias option
------------------

I've received laments that the --alias option of the v3 replicator
disappeared in the v4 replicator.  I've added code intending to support
this, based on my reading of what the v3 code was attempting to accomplish,
but as I never made use of this feature, I may have misunderstood the
actual intent.  Please let me know if I botched up any of: the intent of
the option, its implementation, or its documentation.
