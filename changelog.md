2020-07-19 version 4.0alpha4
----------------------------
  * Major rewrite: use modern {asyncio and aiohttp} instead of custom {Python2
    compatible "fiber.py" and http protocol} code for task management
  * as a side-effect of moving to aiohttp, at least one known bug was squashed:
    replicator will now follow 301 redirects from upstream servers
  * on the other hand, there is a known race condition in the current code;
    testing has not yet shown it to loose data, but this bug does need to be
    tracked down and squashed before a post-alpha release
  * code has been re-arranged to place modules under a `replicator/`
    subdirectory, for cleaner installation (e.g., under `site-perl/`)
  * incidental code clean-up, mostly related to the asyncio+aiohttp rewrite,
    but since the git diff associated with the associated commit was already
    unusable (the changes touched almost everything, so understanding the new
    code is easier than attempting to read the diff), I didn't bother trying to
    keep any tangentially related clean-ups separate
  * Added ability to interject a proxy between the replicator and upstream HTTP
    servers: set the http_proxy environment variable with a suitable URL for
    the proxy, or pass the --external PROXY command-line argument (the latter
    has precedence).  For best functionality the aiohttp_socks package (version
    0.3.1 or higher, which includes the ProxyConnector class) should be
    installed, giving support for  http and socks proxies; if no suitable
    aiohttp_socks package is found, replicator will fall back to using the
    native aiohttp proxy handling code (only supports http proxies).  Note that
    the proxying of FTP requests remains a wishlist item.

2020-04-22 version 4.0alpha3
----------------------------
  * convert to work with Python 3
  * incorporated "transparent proxy" handling from branch
    'transparent-requests' of
    [zahradil's github fork](https://github.com/zahradil/replicator)
  * transfer maintainership to from Gertjan van Zwieten to xedakini;
    code's primary home is now
    [xedakini's repository on github](https://github.com/xedakini/replicator)

xxxx-xx-xx
----------

Active development has ceased. User contributions are still welcome and
considered for merging.

  * changed umask to 022 (Corey Wright: umask.patch)
  * relaxed timefmt constraints in http header
    (Corey Wright: multiple_last-modified_header_formats.patch)
  * fixed long filename issue by hashing excess length


2008-31-01 version 4.0alpha2
----------------------------

This release fixes an omission of the previous one: the inclusion of the GPL
licence file. This clears the way for packaging initiatives on linux
distributions and other operating systems. Other than this just minor fixes;
the serious work unfortunately got lost on a crashed disk.

  * added GPL licence file
  * generalized fiber.py by using generator name instead of hardcoded string
  * removing partial file in cache after 403 forbidden
  * flushing every line in debug mode
  * fix: no longer setting mtime to -1 if server does not send Last-Modified
  * fix: handling empty command lines correctly


2008-01-01 version 4.0alpha1
----------------------------

The first release in more than three years; result of my decision to give up on
existing code and rewrite replicator from scratch. The new version breaks with
python's built-in asyncore framework and replaces it with a much more flexible
'fiber' scheduler based on python generators. For implementation details see
README.devel which is included in the package. To the user the new flexibility
shows as a long new features list, which includes often requested features such
as server-side download resuming, ftp support, bandwidth shaping, ipv6 support.
Known issues have been solved such as the frozen download problem and the race
condition that prevented joining of simultaneously started downloads. Most of
the old functionality is unchanged, except for cache browsing which will be
restored in a later alpha release. For basic usuage instructions please see the
README.user documentation.

The server has been tested on OS X Leopard and Debian Etch, both i386
architectures. Users with access to other platforms or architectures are highly
encouraged to report their findings on the http-replicator-users mailing list.
Note the unit-test script which checks replicator's functionality on 16
different points, using standard gnu tools. Feature requests and general
discussion are preferably sent to the mailing list as well.

  * rewrite from scratch
  * replaced restrictive asyncore scheduler with new 'fiber' system
  * new feature: server-side download resuming
  * new feature: fpt support
  * new feature: bandwidth shaping
  * new feature: ipv6 support
  * new feature: frozen transactions killed after configurable timeout
  * new feature: rudimentary off-line mode
  * fixed race condition that prevented joining of simultaneously started downloads
  * currently missing feature: cache browsing


2004-11-27 version 3.0
----------------------

  * new feature: cache brower on proxy address
  * new feature: client-side support for partial content
  * added alias option for caching mirrors on same location
  * added check to prevent access outside of cache through symlinks
  * added header length restriction to fight infinite request server attacks
  * created man pages for http-replicator and http-replicator_maintenance
  * fixed timestamp bug; files are now properly closed before changing mtime
  * suppressed size warning for chunked data


2004-08-15 version 2.1
----------------------

  * integrated daemon code in http-replicator
  * changed init.d and cron script to bash
  * moved settings from configuration file to /etc/default/http-replicator
  * introduced optparse module for command line parsing
  * introduced logging module for output
  * added support for an external proxy server
  * added support for an external proxy requiring authentication


2004-05-01 version 2.0
----------------------

  * added support for HTTP/1.1
  * replicator is now suitable for maintaining a gentoo package cache
  * fixed problem with absolute urls
  * added posting support
  * added support for servers that use LF in header instead of CRLF
  * added a command line system
  * fixed security issues
  * improved traceback message for unhandled exceptions
  * fixed problem with incomplete files after a server crash
  * fixed problems with select
  * fixed size calculation in cron script


2004-02-06 version 1.0
----------------------

  * initial release.
