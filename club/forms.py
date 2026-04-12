from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.utils import timezone

from .models import BoardGame, Event, Vote

User = get_user_model()


class UserManageForm(forms.ModelForm):
    is_organizer = forms.BooleanField(required=False)
    is_site_admin = forms.BooleanField(required=False)

    class Meta:
        model = User
        fields = ['is_organizer', 'is_site_admin']


class UserAddForm(forms.ModelForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ['username', 'email']


class SetPasswordForm(forms.Form):
    new_password1 = forms.CharField(
        label='New password',
        widget=forms.PasswordInput,
    )
    new_password2 = forms.CharField(
        label='Confirm password',
        widget=forms.PasswordInput,
    )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('new_password1') != cleaned_data.get('new_password2'):
            raise forms.ValidationError('Passwords do not match.')
        return cleaned_data


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ['username', 'email']


class EmailOrUsernameLoginForm(AuthenticationForm):
    username = forms.CharField(label='Email or Username')


class BoardGameForm(forms.ModelForm):
    bgg_id = forms.IntegerField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = BoardGame
        fields = ['name', 'description', 'min_players', 'max_players', 'bgg_id']


class EventForm(forms.ModelForm):

    class Meta:
        model = Event
        fields = ['title', 'date', 'location', 'description']
        widgets = {
            'date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def clean_date(self):
        date = self.cleaned_data.get('date')
        if date and date < timezone.now():
            raise forms.ValidationError('The event date cannot be in the past.')
        return date


class VoteForm(forms.ModelForm):

    class Meta:
        model = Vote
        fields = ['board_game', 'rank']
