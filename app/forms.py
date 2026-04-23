from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, FloatField, SelectField, SubmitField, PasswordField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

class ItemForm(FlaskForm):
    title = StringField('Titre', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description', validators=[DataRequired()])
    price = FloatField('Prix (Ar)', validators=[DataRequired(), NumberRange(min=0)])
    category = SelectField('Catégorie', choices=[
        ('voitures', 'Voitures'),
        ('motos', 'Motos'),
        ('guitares', 'Guitares'),
        ('vêtements', 'Vêtements'),
        ('autres', 'Autres')
    ], validators=[DataRequired()])
    image = FileField('Image', validators=[FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images seulement')])
    tags = StringField('Tags (séparés par des virgules)', validators=[Optional(), Length(max=200)])  # <-- AJOUT
    submit = SubmitField('Enregistrer')

class AdminLoginForm(FlaskForm):
    password = PasswordField('Mot de passe admin', validators=[DataRequired()])
    submit = SubmitField('Se connecter')