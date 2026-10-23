<?php
/***********************************************
* File      :   config.php
* Project   :   Z-Push
* Descr     :   CalDAV backend configuration file
************************************************/

define('CALDAV_PROTOCOL', 'https');
define('CALDAV_SERVER', '127.0.0.1');
define('CALDAV_PORT', '443');
define('CALDAV_PATH', '/caldav/calendars/%u/');
define('CALDAV_PERSONAL', 'PRINCIPAL');
define('CALDAV_SUPPORTS_SYNC', false);
define('CALDAV_MAX_SYNC_PERIOD', 2147483647);

// PHP >= 8.0 removed MBSTRING_OVERLOAD together with mbstring.func_overload,
// but Z-Push 2.7.7 include/z_RTF.php (byte_strlen/byte_substr) still reads it.
// Without this, any RTF body sent by a client ends the Sync request with a
// fatal "Undefined constant" error. 0 makes z_RTF use plain strlen/substr.
if (!defined('MBSTRING_OVERLOAD')) define('MBSTRING_OVERLOAD', 0);

?>
