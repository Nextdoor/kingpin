##### hipchat.Topic

Sets a HipChat room topic.

**Options**

  * `room` - The string-name (or ID) of the room to set the topic of
  * `topic` - String of the topic to send

Examples

    { 'room': 'Operations', 'topic': 'Latest Deployment: v1.2' }

**Dry Mode**

Fully supported -- does not actually set a room topic, but validates
that the API credentials would have access to set the topic of the room
requested.
