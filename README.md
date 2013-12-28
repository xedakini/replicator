HTTP Replicator
===============

HTTP Replicator is a general purpose caching proxy server written in python. It
reduces bandwidth by merging concurrent downloads and building a local
'replicated' file hierarchy, similar to wget -r. The cache will also be
accessible through a web interface; currently unsupported.

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

Replicator has reasonable defaults for all its settings, which means it can be
run without command line arguments. In that case it will listen at port 8080,
will not detach from the terminal, and takes the current directory as root.
Files are cached in top directory host:port, where port defaults to 80 for http
and 21 for ftp, and a trailing path corresponding to the url. The following
arguments can be used to change this default behaviour:

  * -h --help

    Show this help message and exit.
 
  * -p --port PORT

    Listen on this port for incoming connections, default 8080.
 
  * -r --root DIR

    Set cache root directory, default current.
 
  * -v --verbose

    Show http headers and other info
 
  * -t --timeout SEC

    Break connection after so many seconds of inactivity, default 15
 
  * -6 --ipv6

    Try ipv6 addresses if available
 
  * --flat

    Flat mode; cache all files in root directory (dangerous!)
 
  * --static

    Static mode; assume files never change
 
  * --offline

    Offline mode; never connect to server
 
  * --limit RATE

    Limit download rate at a fixed K/s
 
  * --daemon LOG

    Route output to log and detach
 
  * --debug

    Switch from gather to debug output module
