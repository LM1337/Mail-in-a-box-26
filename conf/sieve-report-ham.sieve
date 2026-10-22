require ["vnd.dovecot.pipe", "copy", "imapsieve", "environment", "variables"];

if environment :matches "imap.mailbox" "*" {
  set "mailbox" "${1}";
}

# Do not learn ham when a message goes to Trash (22.04 antispam: "trash;Deleted *",
# ignoring case) or to another spam folder (Spam->Junk would learn ham and spam at once).
if anyof (string :comparator "i;ascii-casemap" "${mailbox}" ["Trash", "Spam", "Junk"],
          string :comparator "i;ascii-casemap" :matches "${mailbox}" ["Deleted *", "Trash/*", "Trash.*"]) {
  stop;
}

if environment :matches "imap.user" "*" {
  set "username" "${1}";
}

pipe :copy "sa-learn-ham.sh" [ "${username}" ];
