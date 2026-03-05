# shopping_app/forms.py

from django import forms
from .models import SellerVerification   # once appended to models.py


class SellerVerificationForm(forms.ModelForm):

    date_of_birth = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label='Date of Birth',
    )

    class Meta:
        model  = SellerVerification
        fields = [
            # Section 1 — Personal
            'full_legal_name', 'national_id_number', 'date_of_birth',
            'phone_number', 'physical_address', 'district', 'country',
            # Section 2 — Business
            'business_name', 'business_registration_no', 'business_type',
            'business_address', 'tin_number',
            # Section 3 — Documents
            'national_id_front', 'national_id_back', 'selfie_with_id',
            'business_cert', 'proof_of_address',
        ]
        widgets = {
            'physical_address': forms.Textarea(attrs={'rows': 3}),
            'business_address': forms.Textarea(attrs={'rows': 3}),
        }
        labels = {
            'national_id_number':       'National ID / Passport Number',
            'business_registration_no': 'Business Registration Number (if applicable)',
            'tin_number':               'TIN Number (if applicable)',
            'national_id_front':        'National ID — Front Photo',
            'national_id_back':         'National ID — Back Photo',
            'selfie_with_id':           'Selfie Holding Your ID',
            'business_cert':            'Business Certificate (if applicable)',
            'proof_of_address':         'Proof of Address (utility bill / letter)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Optional document fields
        optional_docs = ['national_id_back', 'selfie_with_id', 'business_cert', 'proof_of_address']
        for f in optional_docs:
            self.fields[f].required = False

        # Required: front ID only
        self.fields['national_id_front'].required = True

        # Consistent dark-theme CSS across all fields
        base_classes = (
            'w-full border-2 border-white bg-black text-white '
            'px-3 py-2 text-sm font-bold focus:outline-none focus:border-primary'
        )
        for field in self.fields.values():
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (existing + ' ' + base_classes).strip()