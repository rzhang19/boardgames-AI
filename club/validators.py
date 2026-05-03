import re

from django.core.exceptions import ValidationError


class HasLetterAndDigitValidator:
    def validate(self, password, user=None):
        if not re.search(r'[a-zA-Z]', password):
            raise ValidationError(
                'The password must contain at least one letter.',
                code='password_no_letter',
            )
        if not re.search(r'\d', password):
            raise ValidationError(
                'The password must contain at least one digit.',
                code='password_no_digit',
            )

    def get_help_text(self):
        return 'Your password must contain at least one letter and one digit.'
