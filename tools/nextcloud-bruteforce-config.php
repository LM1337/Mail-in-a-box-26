<?php
// Mail-in-a-Box (fork): reads and sets Nextcloud's brute-force settings in
// config.php, for management/nextcloud_throttle.py (System > Intrusion
// Protection in the control panel, and setup/start.sh).
//
// Runs as www-data, which owns config.php and its directory, with this script
// on standard input (www-data cannot read the Mail-in-a-Box directory):
//
//   NC_CONFIG=$STORAGE_ROOT/owncloud/config.php [NC_SET='{"auth.bruteforce.max-attempts": 12}'] \
//     runuser -u www-data -- php8.5 < tools/nextcloud-bruteforce-config.php
//
// NC_SET is a JSON object of the keys below; null removes a key (Nextcloud's
// default applies again). Other keys are refused. The file is replaced
// atomically (a new file in the same directory, renamed over it), as
// setup/nextcloud.sh writes it (B124): Nextcloud reads config.php on every
// request, and "occ config:system:set" is refused once setup has set
// config_is_read_only. Prints the current values as JSON. Exit code 1: the
// file could not be read or written, 2: invalid NC_SET.
//
// Two runs of this script (the control panel and setup) are serialized with
// a lock file next to config.php, so that one does not write back what it
// read before the other's change. The other writers of config.php (setup's
// own block in setup/nextcloud.sh, Nextcloud while config_is_read_only is
// off during setup) do not take the lock; they do not run at the same time
// as the control panel's save in practice.

$path = getenv('NC_CONFIG');
if ($path === false || $path === '') {
  fwrite(STDERR, "NC_CONFIG is not set.\n");
  exit(1);
}
$lock = @fopen(dirname($path) . '/.config.php.mailinabox-lock', 'c');
if ($lock === false || !flock($lock, LOCK_EX)) {
  fwrite(STDERR, "Nextcloud: could not lock " . dirname($path) . "/.config.php.mailinabox-lock.\n");
  exit(1);
}
if ((include $path) === false || !isset($CONFIG) || !is_array($CONFIG)) {
  fwrite(STDERR, "Nextcloud: www-data cannot read $path.\n");
  exit(1);
}

$keys = array(
  'auth.bruteforce.protection.enabled' => 'bool',
  'auth.bruteforce.max-attempts' => 'int',
);

$set = getenv('NC_SET');
if ($set !== false && $set !== '') {
  $values = json_decode($set, true);
  if (!is_array($values)) {
    fwrite(STDERR, "NC_SET is not a JSON object.\n");
    exit(2);
  }
  $changed = false;
  foreach ($values as $key => $value) {
    if (!isset($keys[$key])) {
      fwrite(STDERR, "NC_SET: $key is not a brute-force setting.\n");
      exit(2);
    }
    if ($value === null) {
      if (array_key_exists($key, $CONFIG)) { unset($CONFIG[$key]); $changed = true; }
    } elseif ($keys[$key] === 'bool' && is_bool($value)) {
      if (!array_key_exists($key, $CONFIG) || $CONFIG[$key] !== $value) { $CONFIG[$key] = $value; $changed = true; }
    } elseif ($keys[$key] === 'int' && is_int($value) && $value >= 1 && $value <= 100000) {
      if (!array_key_exists($key, $CONFIG) || $CONFIG[$key] !== $value) { $CONFIG[$key] = $value; $changed = true; }
    } else {
      fwrite(STDERR, "NC_SET: invalid value for $key.\n");
      exit(2);
    }
  }
  if ($changed) {
    $tmp = tempnam(dirname($path), '.config.php.');
    if ($tmp === false || dirname($tmp) !== dirname($path)
        || file_put_contents($tmp, "<?php\n\$CONFIG = " . var_export($CONFIG, true) . ";\n") === false
        || !rename($tmp, $path)) {
      if ($tmp !== false) { @unlink($tmp); }
      fwrite(STDERR, "Nextcloud: could not write $path.\n");
      exit(1);
    }
    // PHP-FPM notices the new file within a second (opcache.revalidate_freq=1,
    // setup/nextcloud.sh).
  }
}

echo json_encode(array(
  // As stored (null: not set), and as Nextcloud reads them
  // (getSystemValueBool and getSystemValueInt cast: 0, '0' and '' are off,
  // 'false' is on).
  'enabled' => array_key_exists('auth.bruteforce.protection.enabled', $CONFIG) ? $CONFIG['auth.bruteforce.protection.enabled'] : null,
  'enabled_effective' => (bool)(array_key_exists('auth.bruteforce.protection.enabled', $CONFIG) ? $CONFIG['auth.bruteforce.protection.enabled'] : true),
  'max_attempts' => array_key_exists('auth.bruteforce.max-attempts', $CONFIG) ? $CONFIG['auth.bruteforce.max-attempts'] : null,
  'max_attempts_effective' => (int)(array_key_exists('auth.bruteforce.max-attempts', $CONFIG) ? $CONFIG['auth.bruteforce.max-attempts'] : 10),
  'force_database' => !empty($CONFIG['auth.bruteforce.protection.force.database']),
  'memcache_distributed' => isset($CONFIG['memcache.distributed']) ? (string)$CONFIG['memcache.distributed'] : null,
  'dbtype' => isset($CONFIG['dbtype']) ? (string)$CONFIG['dbtype'] : null,
  'dbtableprefix' => isset($CONFIG['dbtableprefix']) ? (string)$CONFIG['dbtableprefix'] : 'oc_',
  'datadirectory' => isset($CONFIG['datadirectory']) ? (string)$CONFIG['datadirectory'] : null,
  // The size of the IPv6 networks Nextcloud counts (IpAddress::getIPv6Subnet).
  'ipv6_prefix' => min(64, max(32, isset($CONFIG['security.ipv6_normalized_subnet_size']) ? (int)$CONFIG['security.ipv6_normalized_subnet_size'] : 56)),
)), "\n";
