<?php

/**
 * Mail-in-a-Box password driver for Roundcube's password plugin (fork, B210).
 *
 * Installed by setup/webmail.sh as plugins/password/drivers/mailinabox.php
 * ($config['password_driver'] = 'mailinabox'). Do not edit: setup writes it
 * again on every run.
 *
 * Changes the password of the logged-in user through the management daemon
 * (POST http://127.0.0.1:10222/me/password), which checks the current
 * password and applies the box's password policy and hash. Roundcube's sql
 * driver wrote users.sqlite itself as www-data, so www-data had to be able
 * to write the whole user database. The daemon's answer:
 *   200 "OK"      the password was changed
 *   400 message   the new password was refused (policy)
 *   403 message   the current password is wrong, or the account uses
 *                 two-factor authentication (an administrator changes it in
 *                 the control panel)
 *   429 message   too many failed attempts
 * The client's address goes in X-Forwarded-For, so that a failed attempt is
 * logged for it (fail2ban's miab-management jail).
 */

class rcube_mailinabox_password
{
    public function save($curpass, $newpass, $username)
    {
        $url = 'http://127.0.0.1:10222/me/password';
        $headers = [];
        $remote = $_SERVER['REMOTE_ADDR'] ?? '';
        if (filter_var($remote, FILTER_VALIDATE_IP) !== false) {
            $headers['X-Forwarded-For'] = $remote;
        }

        try {
            $client = password::get_http_client();
            $response = $client->post($url, [
                'auth' => [$username, $curpass],
                'form_params' => ['password' => $newpass],
                'headers' => $headers,
                'http_errors' => false,
                'allow_redirects' => false,
            ]);
            $code = $response->getStatusCode();
            $body = trim(substr((string) $response->getBody(), 0, 1024));
        } catch (\Exception $e) {
            rcube::raise_error('Password plugin (mailinabox): ' . $e->getMessage(), true);
            return PASSWORD_CONNECT_ERROR;
        }

        if ($code == 200 && $body === 'OK') {
            return PASSWORD_SUCCESS;
        }
        // One line of plain text from the daemon, shown to the user.
        $message = preg_replace('/[\x00-\x1F\x7F]+/', ' ', $body);
        if ($code == 400) {
            return ['code' => PASSWORD_CONSTRAINT_VIOLATION, 'message' => $message];
        }
        if ($code == 403 || $code == 429) {
            return ['code' => PASSWORD_ERROR, 'message' => $message];
        }
        rcube::raise_error("Password plugin (mailinabox): unexpected answer {$code} of the management daemon: {$message}", true);
        return PASSWORD_CONNECT_ERROR;
    }
}
