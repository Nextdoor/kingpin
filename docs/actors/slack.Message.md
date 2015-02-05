##### slack.Message

Sends a message to a channel in Slack.

**Options**

  * `channel` - The string-name of the channel to send a message to
  * `message` - String of the message to send

Examples

    { 'room': '#operations', 'message': 'Beginning Deploy: v1.2' }

**Dry Mode**

Fully supported -- does not actually send messages to a room, but validates
that the API credentials would have access to send the message using the
Slack `auth.test` API method.
