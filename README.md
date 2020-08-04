HTTP Replicator
===============

HTTP Replicator is a general purpose caching proxy server written in python.
It reduces bandwidth by merging concurrent downloads and building a local
'replicated' file hierarchy, similar to `wget -r`.

The following example session demonstrates basic usage.

       ~$ mkdir /tmp/cache
       ~$ http-replicator -r /tmp/cache -p 8888 --daemon /tmp/replicator.log
       [process id]
       ~$ http_proxy=localhost:8888 wget http://www.python.org/index.html
       100%[====================================>] 15,978
       ~$ find /tmp/cache
       /tmp/cache
       /tmp/cache/www.python.org:80
       /tmp/cache/www.python.org:80/index.html


Dependencies
------------

This version of HTTP Replicator has the following dependencies:

  * python, version 3.6 or higher (only tested against python 3.7)
  * aiohttp (only tested against aiohttp 3.6.2), and its many dependencies
  * aiohttp-socks is required if the --external PROXY option is used
    (otherwise it is not required); if used, version 0.3.1 or higher
    is needed (only tested against aiohttp-socks 0.5.3)


Use as a transparent proxy
--------------------------

HTTP Replicator can be used also as transparent proxy if traffic is redirected
by iptables:

       iptables -t nat -A OUTPUT -p tcp -m owner ! --uid-owner <user> \
                --dport 80 -j REDIRECT --to-port <port>

Then you can use just simple command without http\_proxy variable:

       wget http://www.python.org/index.html

The `<user>` in this example must be user who run the http-replicator and this
user must differ from user who is sending requests (wget, curl ...). `<port>`
is http-replicator port.


Access control
--------------
There are three mechanisms to restrict access to the HTTP replicator:

  * use --bind with an on-server address which is local-only
  * use --ip with addresses or networks (CIDR notation) which are
    permitted
  * use firewall rules (e.g., iptables, nftables, pf)

Only requests that are permitted by all three mechanisms will be honored.

### --bind
If the local network topology has not-routable-to-the-internet address ranges
(such as an IPv6 ULA within fc00::/7 that is not NAT-ed to the outside
world), then binding to such an address is an easy way to restrict access
to the local network (for varying administrative definitions of "local",
depending on the routing tables being used).

### --ip
The --ip option allows one to select specific addresses and subnets
to which one is willing to grant access.  Using --bind with a wildcard
address and --ip with a local network CIDR can (depending on the details)
be considered two approaches to the same goal: using --bind focuses on
"any subnet which can reach the server via this address may connect",
while --ip focuses on "only allow requests from this subnet to connect".

### firewall rules
Firewall languages give one the greatest flexibility in filtering
out unwanted connections; they can make connection decisions based on
more information than just the source and/or destination IP address.
Their flexibility can make them a little more difficult to work with,
though often using something like "ipset" rules can make them reasonably
straightforward. For example, using ip6tables and ipset, and assuming the
replicator is running on port 8080:

       ipset create ip6-allow hash:net,port family inet7
       ip6tables -A INPUT -m set --match-set ip6-allow src,dst -j ACCEPT
       ipset add ip6-allow fd42:dead:beef::/48,8080

Here, the destination port 8080 is included in this set so that the
iptables rule can be used for services beyond just the HTTP replicator.
We enable access from the fd42:dead:beef::/48 ULA subnet, and can easily
add (or delete or change) the permitted subnets (on a per-destination-port
basis) by suitable use of the ipset command to modify the ip6-allow set.
[Note: the "-A INPUT" used in this example may not be the appropriate
place to add the "-m set" rule, depending on how the rest of the iptables
firewall rules are set up.  It was chosen for explicatory expediency as
one plausible placement, but please do *not* blindly copy it into your
own local configuration.]

One other consideration is that working with firewall rules will almost
certainly require administrative privileges, whereas the --bind and --ip
options work fine even if the replicator is run by an ordinary user.


Command-line usage
------------------

Replicator has reasonable defaults for all its settings, which means it can be
run without command line arguments. In that case it will listen at port 8080,
will not detach from the terminal, and takes the current directory as root.
Files are cached in top directory host:port, where port defaults to 80 for http
and 21 for ftp, and a trailing path corresponding to the url. The following
arguments can be used to change this default behavior:

       -h --help
        Show this help message and exit.

       -b --bind ADDRESS
        Bind server to ADDRESS.  ADDRESS may be a wildcard (:: for IPv6,
        0.0.0.0 for IPv4).  --bind may be specified more than once to
        listen on multiple ADDRESSes.  If zero --bind options are given,
        defaults to the local address ::1.

       -p --port PORT
        Listen on this port for incoming connections, default 8080.

       -r --root DIR
        Set cache root directory, default current.

       --external PROXYURL, -e PROXYURL
        Forward requests through an external proxy server; aiohttp-socks
        (version 0.3.1 or greater) must be installed for this to work.

       --ip CIDR, -i CIDR
        Restrict incoming requests to be from specified CIDR (IPv4 or
        IPv6).  This option may be repeated if more than one CIDR is
        acceptable.  If no --ip option is given, defaults to allowing
        all requests, regardless of source IP address.

       --alias MAPPING, -a MAPPING
        ((coming soon; not yet implemented))

       -v --verbose
        Show http headers and other info

       -t --timeout SEC
        Break connection after so many seconds of inactivity, default 15

       --flat
        Flat mode; cache all files in root directory (dangerous!)

       --static
        Static mode; assume files never change

       --offline
        Offline mode; never connect to server

       --limit RATE
        Limit download rate at a fixed K/s

       --daemon LOG
        Route output to log and detach

       --pid PIDFILE
        if --daemon is used, write pid of daemon to PIDFILE
