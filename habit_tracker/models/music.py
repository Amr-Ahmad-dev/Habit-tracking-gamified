from extensions import db


class Track(db.Model):
    __tablename__ = "tracks"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(20), nullable=False)  # focus, gym, sleep
    filename = db.Column(db.String(255), nullable=False)  # relative to static/music/<category>/
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
