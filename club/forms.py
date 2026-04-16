from datetime import datetime, time as dt_time

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.utils import timezone

from .models import BoardGame, Event, Vote
from .timezone_utils import get_timezone_choices, is_valid_timezone

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
    email = forms.EmailField(required=False)

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
    date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={'type': 'time'}),
    )
    voting_deadline_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    voting_deadline_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={'type': 'time'}),
    )

    class Meta:
        model = Event
        fields = ['title', 'location', 'description']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.date:
            self.fields['date'].initial = self.instance.date.date()
            if self.instance.date.time() != dt_time(0, 0):
                self.fields['time'].initial = self.instance.date.time()
            if self.instance.voting_deadline:
                self.fields['voting_deadline_date'].initial = self.instance.voting_deadline.date()
                if self.instance.voting_deadline.time() != dt_time(0, 0):
                    self.fields['voting_deadline_time'].initial = self.instance.voting_deadline.time()

    def clean(self):
        cleaned_data = super().clean()
        date_val = cleaned_data.get('date')
        time_val = cleaned_data.get('time') or dt_time(0, 0)
        if date_val:
            combined = datetime.combine(date_val, time_val)
            combined = timezone.make_aware(combined) if timezone.is_naive(combined) else combined
            original_date = getattr(self.instance, 'date', None)
            is_same_datetime = (
                original_date
                and combined.date() == original_date.date()
                and combined.hour == original_date.hour
                and combined.minute == original_date.minute
            )
            if combined < timezone.now() and not is_same_datetime:
                self.add_error('date', 'The event date cannot be in the past.')
            cleaned_data['date'] = combined

        vd_date = cleaned_data.get('voting_deadline_date')
        vd_time = cleaned_data.get('voting_deadline_time') or dt_time(0, 0)
        if vd_date:
            vd_combined = datetime.combine(vd_date, vd_time)
            vd_combined = timezone.make_aware(vd_combined) if timezone.is_naive(vd_combined) else vd_combined
            event_date = cleaned_data.get('date')
            if event_date:
                if vd_combined > event_date:
                    self.add_error('voting_deadline_date', 'Voting deadline cannot be after the event start time.')
            buffer = timezone.now() + timezone.timedelta(minutes=2)
            original_deadline = getattr(self.instance, 'voting_deadline', None)
            deadline_unchanged = (
                original_deadline
                and vd_combined.date() == original_deadline.date()
                and vd_combined.hour == original_deadline.hour
                and vd_combined.minute == original_deadline.minute
            )
            if vd_combined < buffer and not deadline_unchanged:
                self.add_error('voting_deadline_date', 'Voting deadline must be at least 2 minutes from now.')
            cleaned_data['voting_deadline'] = vd_combined
        else:
            cleaned_data['voting_deadline'] = None

        return cleaned_data


class VoteForm(forms.ModelForm):

    class Meta:
        model = Vote
        fields = ['board_game', 'rank']


class SettingsForm(forms.Form):
    email = forms.EmailField(required=False)
    timezone = forms.ChoiceField(
        choices=get_timezone_choices,
        initial='UTC',
    )

    def clean_timezone(self):
        tz = self.cleaned_data['timezone']
        if not is_valid_timezone(tz):
            raise forms.ValidationError('Invalid timezone.')
        return tz


class BetaAccessForm(forms.Form):
    access_code = forms.CharField(
        widget=forms.PasswordInput(attrs={'autofocus': True}),
    )
