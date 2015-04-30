##### slack.Message

Sends a message to a channel in Slack.

**Options**

  * `channel` - The string-name of the channel to send a message to
  * `message` - String of the message to send

Examples

    { "desc": "Let the Engineers know things are happening",
      "actor": "slack.Message",
      "options": {
        "channel": "#operations",
        "message": "Beginning Deploy: %VER%"
      }
    }

**Dry Mode**

Fully supported -- does not actually send messages to a room, but validates
that the API credentials would have access to send the message using the
Slack `auth.test` API method.
