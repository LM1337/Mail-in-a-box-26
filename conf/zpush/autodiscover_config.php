<?php
/***********************************************
* File      :   config.php
* Project   :   Z-Push
* Descr     :   Autodiscover configuration file
************************************************/

define('TIMEZONE', '');

// Defines the base path on the server
define('BASE_PATH', dirname($_SERVER['SCRIPT_FILENAME']). '/');

define('ZPUSH_HOST', 'PRIMARY_HOSTNAME');

define('USE_FULLEMAIL_FOR_LOGIN', true);

define('LOGFILEDIR', '/var/log/z-push/');
define('LOGFILE', LOGFILEDIR . 'autodiscover.log');
define('LOGERRORFILE', LOGFILEDIR . 'autodiscover-error.log');
define('LOGLEVEL', LOGLEVEL_INFO);
define('LOGUSERLEVEL', LOGLEVEL);
$specialLogUsers = array();

// the backend data provider
define('BACKEND_PROVIDER', 'BackendCombined');

// Z-Push 2.7.7 reads DAV_SSL_VERIFY in its CalDAV/CardDAV client, but only the
// main config.php defines it and autodiscover does not load that file, so every
// autodiscover request ended in a fatal error. AUTO verifies certificates except
// on loopback, which is where our CalDAV/CardDAV backends connect (127.0.0.1).
if (!defined('DAV_SSL_VERIFY')) define('DAV_SSL_VERIFY', DAV_SSL_VERIFY_AUTO);
?>
