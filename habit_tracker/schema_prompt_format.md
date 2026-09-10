# One-Prompt Template Import Format

Paste JSON matching this shape into **Templates → One-prompt import**. Give the
prompt below to any AI (Claude, ChatGPT, etc.) to generate it for you.

## Schema

```
{
  "template": {
    "title": "string (required)",
    "description": "string or null",
    "scope": "lifelong" | "weekly" | "daily",
    "weekday": "MO"|"TU"|"WE"|"TH"|"FR"|"SA"|"SU" | null,
    "start_time": "HH:MM" | null,
    "end_time": "HH:MM" | null,
    "recurrence": "indefinite" | "weekly" | "daily" | "once",
    "difficulty": 1-5,
    "category": "Physical" | "Mental" | "Financial" | "Growth" | null,
    "children": [ /* zero or more nodes of this same shape - this is what
                     makes the template recursive: a block inside a block */ ]
  }
}
```

Only leaf nodes (nodes with `weekday` set and no children) turn into actual
scheduled tasks when the template is instantiated. Container nodes
(`scope: "lifelong"` or `"weekly"` with children) exist purely for
organization and don't need a weekday/time.

## Example: lifelong "Study Block" containing a weekly per-subject plan

```json
{
  "template": {
    "title": "Study Block",
    "scope": "lifelong",
    "recurrence": "indefinite",
    "difficulty": 3,
    "category": "Mental",
    "children": [
      {
        "title": "Calculus",
        "scope": "weekly",
        "weekday": "MO",
        "start_time": "16:00",
        "end_time": "18:00",
        "recurrence": "weekly",
        "difficulty": 3,
        "category": "Mental"
      },
      {
        "title": "Physics",
        "scope": "weekly",
        "weekday": "WE",
        "start_time": "16:00",
        "end_time": "18:00",
        "recurrence": "weekly",
        "difficulty": 3,
        "category": "Mental"
      }
    ]
  }
}
```

## Copy-paste prompt for any AI

> Generate a JSON object for a habit-tracker recursive template, following
> exactly this schema: `{"template": {"title": str, "description": str|null,
> "scope": "lifelong"|"weekly"|"daily", "weekday": "MO".."SU"|null,
> "start_time": "HH:MM"|null, "end_time": "HH:MM"|null, "recurrence":
> "indefinite"|"weekly"|"daily"|"once", "difficulty": 1-5, "category":
> "Physical"|"Mental"|"Financial"|"Growth"|null, "children": [ ...same
> shape... ]}}`. Build it for: *[describe your plan]*. Return ONLY the JSON,
> no prose.
