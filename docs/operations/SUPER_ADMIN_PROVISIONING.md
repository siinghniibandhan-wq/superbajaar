# Initial Super Admin provisioning

The first Super Admin is created by the operator-run script
`backend/scripts/provision_super_admin.py`. It uses the same password hashing
function as the normal staff login endpoint and does not add a backdoor login.

## Interactive execution

Run from `backend/` with the production environment loaded in a trusted
interactive terminal:

```bash
python scripts/provision_super_admin.py
```

The script prompts for the full name and password, confirms the password, and
never accepts the password as a command-line argument or logs it.

## Non-interactive AWS Systems Manager Run Command

Run Command has no reliable interactive terminal input. For this mode, use an
AWS Systems Manager Parameter Store **SecureString** as a one-time password
source. Do not put the password in `backend.env`, a shell command, command
arguments, or ordinary SSM String parameters.

Configure these non-secret values in the backend environment file:

```ini
SB_SUPER_ADMIN_EMAIL=kpmcenterprise@gmail.com
SB_SUPER_ADMIN_FULL_NAME="Your Full Name"
SB_SUPER_ADMIN_PASSWORD_PARAMETER=/superbajaar/bootstrap/super-admin-password
```

Create the Parameter Store parameter in the same AWS Region as the EC2
instance:

- Name: `/superbajaar/bootstrap/super-admin-password`
- Tier: Standard
- Type: **SecureString**
- Value: the chosen password (minimum 12 characters)

The EC2 instance profile role must be allowed to retrieve and delete only this
parameter. Scope the following policy to the exact parameter ARN:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["ssm:GetParameter", "ssm:DeleteParameter"],
      "Resource": "arn:aws:ssm:us-east-1:<ACCOUNT_ID>:parameter/superbajaar/bootstrap/super-admin-password"
    }
  ]
}
```

If the SecureString uses a customer-managed KMS key, also grant
`kms:Decrypt` on that exact key. The script requests decryption from Parameter
Store, validates that the parameter is a SecureString, and does not print its
value. It deletes the parameter only after the database transaction commits.
If cleanup fails, the script reports that the account was created but the
parameter still needs manual deletion.

Execute from the EC2 instance using the production backend working directory,
virtual environment, and systemd environment file:

```bash
sudo systemd-run --wait --pipe --collect --unit=sb-super-admin-provision \
  -p User=ubuntu \
  -p WorkingDirectory=/opt/superbajaar/source/backend \
  -p EnvironmentFile=/etc/superbajaar/backend.env \
  /opt/superbajaar/source/backend/venv/bin/python scripts/provision_super_admin.py
```

The command prints only the provisioned email and user ID, never the password.
If a Super Admin already exists, provisioning is refused and the SecureString
is retained. Use the normal user-management flow to change an existing
administrator's password.
