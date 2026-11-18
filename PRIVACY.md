# Privacy

StudyAtrium CLI is a command line tool and terminal UI that runs on your own computer. The
maintainers of this repository operate no server and receive no data from it. Statements
below are based on the code in `src/studylife_cli`.

## What is stored

- **Credentials** in `~/.config/studylife-cli/credentials.json` (or under `XDG_CONFIG_HOME`):
  the instance URL, the client id and the API key StudyAtrium issued to the CLI when you ran
  `studylife login`. The file is plain text, restricted to your user on POSIX systems (not on
  Windows). The key is limited to the scopes you granted when registering the CLI.
- **Exports** you create with `studylife export` are written as JSON or Markdown files to the
  directory you name. They contain your study data in clear text; protect or delete them
  yourself.

The CLI keeps no other files: no cache, no history, no logs and no telemetry.

## Where data goes

Requests go only to the StudyAtrium instance you logged in to, over the URL you entered, with
your API key. The browser opens for the login approval on that same instance. Nothing is sent
to the maintainers or any third party.

## Retention and deletion

`studylife logout` deletes the local credentials file. It does not revoke the key on the
server: revoke it in StudyAtrium (account settings) to make a copied key unusable. Deleting
your StudyAtrium account revokes it too. The CLI stores nothing on any server, so there is no
purge endpoint. Export files stay until you delete them.

## Contact

Requests about your StudyAtrium data go to the operator of your StudyAtrium instance. Security
issues: see [SECURITY.md](SECURITY.md).