#!/bin/bash
# export_rewe_mail.sh
# Exportiert neue Mails aus dem Mail.app-Ordner "Rewe" als EML-Dateien.

IMPORT_DIR="/Users/marc/Library/Mobile Documents/com~apple~CloudDocs/Claude/Rewe/import"
LOG="/tmp/rewe_mail_export.log"
ID_FILE="$IMPORT_DIR/.exported_ids"

echo "$(date '+%Y-%m-%d %H:%M:%S'): Starte Rewe-Mail-Export..." >> "$LOG"

# ID-Tracking-Datei anlegen falls nicht vorhanden
touch "$ID_FILE"

osascript << APPLESCRIPT
set importDir to "$IMPORT_DIR"
set logFile to "$LOG"
set idFile to "$ID_FILE"

-- Mail muss laufen
if application "Mail" is not running then
    do shell script "echo '$(date '+%Y-%m-%d %H:%M:%S'): Mail.app läuft nicht, überspringe.' >> " & quoted form of logFile
    return
end if

tell application "Mail"
    -- Rewe-Mailbox in allen Accounts suchen
    set targetMailbox to missing value
    repeat with anAccount in accounts
        try
            set mb to mailbox "Rewe" of anAccount
            set targetMailbox to mb
            exit repeat
        on error
        end try
        -- Auch verschachtelte Mailboxen prüfen
        try
            repeat with mb in mailboxes of anAccount
                if name of mb is "Rewe" then
                    set targetMailbox to mb
                    exit repeat
                end if
            end repeat
        on error
        end try
        if targetMailbox is not missing value then exit repeat
    end repeat

    if targetMailbox is missing value then
        do shell script "echo 'FEHLER: Mailbox Rewe nicht gefunden.' >> " & quoted form of logFile
        return
    end if

    set newCount to 0

    repeat with aMessage in messages of targetMailbox
        set msgId to message id of aMessage

        -- Prüfen ob bereits exportiert (exakter Zeilenvergleich)
        set alreadyExported to false
        try
            do shell script "grep -qxF " & quoted form of msgId & " " & quoted form of idFile
            set alreadyExported to true
        on error
            set alreadyExported to false
        end try

        if not alreadyExported then
            -- Dateiname aus Empfangsdatum generieren: YYYY-MM-DD_HH-MM-SS.eml
            set msgDate to date received of aMessage
            set yr to year of msgDate as string
            set mo to (month of msgDate as integer) as string
            set dy to (day of msgDate) as string
            set hr to (hours of msgDate) as string
            set mn to (minutes of msgDate) as string
            set sc to (seconds of msgDate) as string

            if length of mo < 2 then set mo to "0" & mo
            if length of dy < 2 then set dy to "0" & dy
            if length of hr < 2 then set hr to "0" & hr
            if length of mn < 2 then set mn to "0" & mn
            if length of sc < 2 then set sc to "0" & sc

            set baseName to yr & "-" & mo & "-" & dy & "_" & hr & "-" & mn & "-" & sc
            set fileName to baseName & ".eml"
            set filePath to importDir & "/" & fileName

            -- Kollision behandeln (gleicher Timestamp)
            set counter to 1
            try
                do shell script "test -f " & quoted form of filePath
                repeat
                    set fileName to baseName & "_" & counter & ".eml"
                    set filePath to importDir & "/" & fileName
                    try
                        do shell script "test -f " & quoted form of filePath
                        set counter to counter + 1
                    on error
                        exit repeat
                    end try
                end repeat
            end try

            -- EML schreiben
            try
                set msgSource to source of aMessage
                set fileRef to open for access POSIX file filePath with write permission
                write msgSource to fileRef
                close access fileRef

                -- Message-ID als exportiert markieren
                do shell script "echo " & quoted form of msgId & " >> " & quoted form of idFile
                set newCount to newCount + 1
                do shell script "echo '  Exportiert: " & fileName & "' >> " & quoted form of logFile
            on error errMsg
                do shell script "echo 'FEHLER beim Schreiben von " & fileName & ": " & errMsg & "' >> " & quoted form of logFile
                try
                    close access POSIX file filePath
                end try
                -- Leere Datei löschen falls angelegt
                try
                    do shell script "[ -f " & quoted form of filePath & " ] && [ ! -s " & quoted form of filePath & " ] && rm " & quoted form of filePath
                end try
            end try
        end if
    end repeat

    do shell script "echo '$(date '+%Y-%m-%d %H:%M:%S'): Fertig. " & newCount & " neue Mail(s) exportiert.' >> " & quoted form of logFile
end tell
APPLESCRIPT
