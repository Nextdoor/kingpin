##### hipchat.Message

Sends a message to a room in HipChat.

**Options**

  * `room` - The string-name (or ID) of the room to send a message to
  * `message` - String of the message to send

Examples

    { 'room': 'Operations', 'message': 'Beginning Deploy: v1.2' }

**Dry Mode**

Fully supported -- does not actually send messages to a room, but validates
that the API credentials would have access to send the message using the
HipChat `auth_test` optional API argument.
