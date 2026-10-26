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
// Log failed logins ("... login failed for user with email '...' from IP ...")
// for the miab-zpush jail (B126); they go to autodiscover-error.log as well.
define('LOGAUTHFAIL', true);
$specialLogUsers = array();

// the backend data provider
define('BACKEND_PROVIDER', 'BackendCombined');

// Z-Push 2.7.7 reads DAV_SSL_VERIFY in its CalDAV/CardDAV client, but only the
// main config.php defines it and autodiscover does not load that file, so every
// autodiscover request ended in a fatal error. AUTO verifies certificates except
// on loopback, which is where our CalDAV/CardDAV backends connect (127.0.0.1).
if (!defined('DAV_SSL_VERIFY')) define('DAV_SSL_VERIFY', DAV_SSL_VERIFY_AUTO);

// A login that Dovecot or Nextcloud cannot check at that moment is answered
// with 503 and Retry-After (ServiceUnavailableException, setup/zpush.sh, B126),
// which reads RETRY_AFTER_DELAY; like DAV_SSL_VERIFY only the main config.php
// defines it, and without it such a login ended in a fatal error (HTTP 500).
if (!defined('RETRY_AFTER_DELAY')) define('RETRY_AFTER_DELAY', 300);
?>
