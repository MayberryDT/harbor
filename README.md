# Harbor

![Harbor — private chat for Omarchy](docs/images/harbor-cover.png)

Private, invite-only chat for your Omarchy desktop. Send messages, share files and make voice calls without an account or phone number.

Harbor is a fork of [OmaQ by hancore](https://github.com/HANCORE-linux/OmaQ). It keeps the compact native interface and adds room for longer messages and larger attachments.

## What you can do

Harbor gives you:

- direct and group chats, with replies, edits, reactions and message search
- floating chat windows that follow your active Omarchy theme
- direct voice calls, file transfers and inline images
- a terminal client, `harbor-connect`, that shares your desktop identity and history
- private invitation links and QR codes, with no public user directory

Harbor supports messages up to 64 KiB, direct files up to 1 GiB and inline images up to 64 MiB. Group attachments retain their separate limits. Both people need Harbor for expanded payloads.

## Keep your OmaQ contacts

Harbor can exchange ordinary messages with OmaQ clients. Existing invitation links still work.

On the same machine, Harbor uses your existing OmaQ identity, contacts and history. Disable the OmaQ plugin before enabling Harbor. Its detached helper may keep running after the widget closes. Finish active calls and transfers, then use the helper’s guarded shutdown or activation flow before starting Harbor. Harbor requires protocol 17 and will refuse an older running helper. Do not force-stop a helper with pending sends or private groups.

Run one helper for that profile; do not copy a live identity between machines.

The plugin is called `io.zet.harbor`. The helper, invitation scheme and private data directories retain their `omaq` names for compatibility.

## Install on Omarchy

```bash
omarchy plugin add https://github.com/MayberryDT/harbor.git --yes &&
~/.config/omarchy/plugins/io.zet.harbor/install.sh --yes
```

The installer installs dependencies, builds the native helper, adds Harbor to your bar and creates `harbor-connect`. Read the [installation guide](docs/INSTALLATION.md) before replacing an existing OmaQ installation.

Other Linux distributions are not currently supported.

## Start a conversation

1. Open Harbor using the anchor icon in your bar.
2. Choose Invite and share the private link with someone you trust.
3. Ask them to redeem the link in Harbor or a compatible OmaQ client.
4. Review and accept the incoming request.
5. Open the contact to start chatting.

Use the safety code to compare identities through another trusted channel. Keep invitation links private.

To chat from a terminal, run:

```bash
harbor-connect
```

Type `:help` for commands and keyboard shortcuts. The terminal and bar share one local helper.

## Privacy and its limits

Direct text messages use the Signal Double Ratchet over encrypted Tox transport. Groups use Tox encrypted group transport. Direct files use Tox transfers.

Harbor disables UDP discovery and hole punching. Connections use TCP relays, so contacts do not receive each other’s IP addresses. Public bootstrap and relay nodes still handle network connections and metadata.

Harbor has no account service or telemetry. Your identity and history stay on your device. Local history is not an encrypted vault: filesystem permissions protect data outside the optional Tox-save passphrase.

Read the [security guide](docs/SECURITY.md) before relying on Harbor for sensitive conversations.

## Current release scope

This release focuses on local desktop chat. Simultaneous devices, synchronized conversations, an optional encrypted mailbox and recovery backups are development work, not supported release features.

Expanded transfers need Harbor at both ends. Pending expanded transport queues do not survive a helper restart. A queued message is not a delivered message.

The [fork verification notes](docs/HARBOR.md) record the tested helper and repeatable network checks. Testing covered 64 KiB messages, a 12 MiB file and a 4K image. The configured 1 GiB file limit was not tested with a full-size transfer.

## Update or remove Harbor

Use the helper-aware updater so the interface and native helper stay together:

```bash
~/.config/omarchy/plugins/io.zet.harbor/scripts/update-omaq.sh --yes
```

Do not use `omarchy plugin update` for Harbor. See the [installation lifecycle](docs/INSTALLATION.md) for update and recovery details.

To remove the plugin:

```bash
~/.config/omarchy/plugins/io.zet.harbor/scripts/uninstall-omaq.sh
```

The uninstaller asks separately before removing personal data. Keeping it is the default.

## Documentation and credits

- [User guide](docs/USER-GUIDE.md)
- [Installation and updates](docs/INSTALLATION.md)
- [Security and privacy](docs/SECURITY.md)
- [Fork changes and verification](docs/HARBOR.md)
- [Third-party components and artwork](THIRD_PARTY.md)

Harbor builds on OmaQ by hancore and its contributors. This fork is independent and is not an upstream-endorsed release. The cover is an AI-generated illustration, not a screenshot.

The QML plugin uses the [MIT License](LICENSE.MIT). Helper source is GPL-3.0-or-later; the distributed helper binary is [GPL-3.0-only](LICENSE.GPL-3) because it links to `libsignal-protocol-c`. Asset and dependency terms are listed in [Third-party components](THIRD_PARTY.md).
