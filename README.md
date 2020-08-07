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
  * aiohttp-socks is required for SOCKS proxies using the --external PROXY
    (otherwise it is not required); if used, version 0.3.1 or higher
    is needed (only tested against aiohttp-socks 0.5.3)



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
        (version 0.3.1 or greater) is required to use SOCKS proxies

       --ip CIDR, -i CIDR
        Restrict incoming requests to be from specified CIDR (IPv4 or
        IPv6).  This option may be repeated if more than one CIDR is
        acceptable.  If no --ip option is given, defaults to allowing
        all requests, regardless of source IP address.

       --alias MAPPING, -a MAPPING
        A mapping is a sequence DESTPATH:PREFIX1:PREFIX2:..., where if
        the unaliased cache path begins with PREFIX1 or PREFIX2 or ...,
        then said prefix gets replaced by DESTPATH.  More than one --alias
        mapping may be given.  Only the first PREFIX match found (in the
        order given on the command line) will be rewritten.

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


Additional usage hints
----------------------

See the "README-too.md" file for some additional notes on setting up
the replicator for some specific use cases.
