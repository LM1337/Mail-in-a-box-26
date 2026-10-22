#!/bin/bash
# Called by the IMAPSieve report-spam sieve script when a user
# moves or copies a message into the Spam folder.
# author: https://github.com/yeah
#
# Discard sa-learn's progress output and always exit 0, as the 22.04
# sa-learn-pipe.sh did: a failed learning run (e.g. a bayes lock timeout)
# must not be logged as a failed Sieve pipe action (a runtime error).
# stderr is left alone, so the cause can still reach the Dovecot log.
/usr/bin/sa-learn --spam > /dev/null
exit 0
