##### librato.Annotation

Posts an Annotation to Librato.

**Options**

  * `title` - The title of the annotation
  * `description` - The description of the annotation
  * `metric` - Name of the metric to annotate

Examples

    { 'title': 'Deploy', 'description': 'Version: 0001a',
      'metric': 'production_releases' }

**Dry Mode**

Currently does not actually do anything, just logs dry mode.
