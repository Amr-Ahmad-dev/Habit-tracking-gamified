from datetime import datetime, date, timedelta
from extensions import db
from models import Template, Task, SkillCategory

WEEKDAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def _time(s):
    return datetime.strptime(s, "%H:%M").time() if s else None


def _category_id(name):
    if not name:
        return None
    cat = SkillCategory.query.filter_by(name=name).first()
    return cat.id if cat else None


def build_template_tree(user_id: int, node: dict, parent_id=None) -> Template:
    """Recursively builds Template rows from a nested dict (see schema_prompt_format.md)."""
    tpl = Template(
        user_id=user_id,
        parent_id=parent_id,
        title=node["title"],
        description=node.get("description"),
        scope=node.get("scope", "weekly"),
        weekday=node.get("weekday"),
        start_time=_time(node.get("start_time")),
        end_time=_time(node.get("end_time")),
        recurrence=node.get("recurrence", "indefinite"),
        difficulty=int(node.get("difficulty", 1)),
        skill_category_id=_category_id(node.get("category")),
    )
    db.session.add(tpl)
    db.session.flush()  # get tpl.id for children
    for child in node.get("children", []):
        build_template_tree(user_id, child, parent_id=tpl.id)
    return tpl


def import_payload(user_id: int, payload: dict) -> Template:
    """payload = {"template": {...recursive node...}}"""
    root = payload["template"]
    tree = build_template_tree(user_id, root)
    db.session.commit()
    return tree


def instantiate_template(template: Template, weeks_ahead: int = 4) -> int:
    """Turns a (leaf) template with a weekday/time into concrete scheduled
    Task rows for the next `weeks_ahead` occurrences. Container/lifelong
    templates just recurse into their children.
    """
    created = 0
    if template.children:
        for child in template.children:
            created += instantiate_template(child, weeks_ahead)
        return created

    if not template.weekday:
        return created

    today = date.today()
    target_idx = WEEKDAYS.index(template.weekday)
    first = today + timedelta(days=(target_idx - today.weekday()) % 7)
    occurrences = weeks_ahead if template.recurrence in ("weekly", "indefinite") else 1

    for i in range(occurrences):
        d = first + timedelta(weeks=i)
        db.session.add(Task(
            user_id=template.user_id,
            title=template.title,
            description=template.description,
            scheduled_date=d,
            start_time=template.start_time,
            end_time=template.end_time,
            recurrence=template.recurrence,
            difficulty=template.difficulty,
            skill_category_id=template.skill_category_id,
        ))
        created += 1
    db.session.commit()
    return created
