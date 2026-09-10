from extensions import db


class Template(db.Model):
    """A reusable, recursive blueprint (block-inside-block) that can be
    instantiated into real scheduled Tasks. E.g. 'Study Block 4-10' (lifelong)
    containing sub-blocks per weekday/subject.
    """
    __tablename__ = "templates"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("templates.id"), nullable=True)
    skill_category_id = db.Column(db.Integer, db.ForeignKey("skill_categories.id"), nullable=True)

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)

    scope = db.Column(db.String(20), default="weekly")  # lifelong, weekly, daily
    weekday = db.Column(db.String(2), nullable=True)  # MO, TU, WE, TH, FR, SA, SU
    start_time = db.Column(db.Time, nullable=True)
    end_time = db.Column(db.Time, nullable=True)
    recurrence = db.Column(db.String(20), default="indefinite")  # indefinite, weekly, daily, once
    difficulty = db.Column(db.Integer, default=1)

    children = db.relationship(
        "Template", backref=db.backref("parent", remote_side=[id]),
        cascade="all, delete-orphan", single_parent=True,
    )

    def to_dict(self):
        return {
            "title": self.title, "description": self.description, "scope": self.scope,
            "weekday": self.weekday,
            "start_time": self.start_time.strftime("%H:%M") if self.start_time else None,
            "end_time": self.end_time.strftime("%H:%M") if self.end_time else None,
            "recurrence": self.recurrence, "difficulty": self.difficulty,
            "children": [c.to_dict() for c in self.children],
        }
