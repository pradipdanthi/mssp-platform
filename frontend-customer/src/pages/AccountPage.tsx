import { FormEvent, useEffect, useState } from "react";
import { ApiError } from "../api/client";
import { changePassword, updateMyProfile } from "../api/auth";
import { useAuth } from "../auth/AuthContext";
import { useBrand } from "../config/BrandContext";

export default function AccountPage() {
  const { user, setUser } = useAuth();
  const brand = useBrand();

  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [profileMessage, setProfileMessage] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileSaving, setProfileSaving] = useState(false);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSaving, setPasswordSaving] = useState(false);

  useEffect(() => {
    if (!user) {
      return;
    }
    setFullName(user.full_name);
    setPhone(user.phone ?? "");
  }, [user]);

  if (!user) {
    return <div className="state-message">No account information available.</div>;
  }

  async function onSaveProfile(event: FormEvent) {
    event.preventDefault();
    setProfileMessage(null);
    setProfileError(null);
    setProfileSaving(true);
    try {
      const updated = await updateMyProfile({
        full_name: fullName.trim(),
        phone: phone.trim() ? phone.trim() : null,
      });
      setUser(updated);
      setProfileMessage("Profile saved.");
    } catch (err) {
      if (err instanceof ApiError) {
        setProfileError(
          typeof err.detail === "string" ? err.detail : "Unable to save profile. Please try again."
        );
      } else {
        setProfileError("Unable to save profile. Please try again.");
      }
    } finally {
      setProfileSaving(false);
    }
  }

  async function onChangePassword(event: FormEvent) {
    event.preventDefault();
    setPasswordMessage(null);
    setPasswordError(null);

    if (newPassword.length < 8) {
      setPasswordError("New password must be at least 8 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError("New password and confirmation do not match.");
      return;
    }

    setPasswordSaving(true);
    try {
      await changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setPasswordMessage("Password updated. Use the new password next time you sign in.");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      if (err instanceof ApiError) {
        setPasswordError(
          typeof err.detail === "string"
            ? err.detail
            : "Unable to change password. Check your current password and try again."
        );
      } else {
        setPasswordError("Unable to change password. Please try again.");
      }
    } finally {
      setPasswordSaving(false);
    }
  }

  return (
    <div>
      <h1 className="page-title">Account</h1>
      <p className="page-subtitle">
        View your account details. You can update your name and phone, or change your password.
        Your email, role, and tenant are managed by your SOC team.
      </p>

      <div className="account-panel">
        <div className="credential-grid">
          <Field label="Email" value={user.email} />
          <Field label="Role" value={user.role} />
          <Field label="Status" value={user.status} />
          <Field label="Tenant" value={user.tenant_name ?? "Not assigned"} />
          <Field label="Tenant code" value={user.tenant_short_code ?? "Not assigned"} />
          <Field label="Last login" value={user.last_login_at ?? "Never"} />
          <Field label="Portal" value={brand.portalName} />
        </div>
        {!user.tenant_short_code && (
          <div className="state-message state-error" style={{ marginTop: 16 }}>
            This account is not linked to a customer tenant. Customer dashboard data requires a
            tenant-linked customer role.
          </div>
        )}
      </div>

      <form className="account-panel account-form" onSubmit={onSaveProfile}>
        <h2 className="account-form-title">Profile</h2>
        <label className="account-label">
          Name
          <input
            className="account-input"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            required
            maxLength={200}
            autoComplete="name"
          />
        </label>
        <label className="account-label">
          Phone
          <input
            className="account-input"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            maxLength={40}
            autoComplete="tel"
            placeholder="Optional"
          />
        </label>
        {profileError && <div className="state-message state-error">{profileError}</div>}
        {profileMessage && <div className="state-message state-success">{profileMessage}</div>}
        <button className="btn btn-primary" type="submit" disabled={profileSaving}>
          {profileSaving ? "Saving..." : "Save profile"}
        </button>
      </form>

      <form className="account-panel account-form" onSubmit={onChangePassword}>
        <h2 className="account-form-title">Change password</h2>
        <label className="account-label">
          Current password
          <input
            className="account-input"
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            required
            autoComplete="current-password"
          />
        </label>
        <label className="account-label">
          New password
          <input
            className="account-input"
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
          />
        </label>
        <label className="account-label">
          Confirm new password
          <input
            className="account-input"
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
          />
        </label>
        {passwordError && <div className="state-message state-error">{passwordError}</div>}
        {passwordMessage && <div className="state-message state-success">{passwordMessage}</div>}
        <button className="btn btn-primary" type="submit" disabled={passwordSaving}>
          {passwordSaving ? "Updating..." : "Update password"}
        </button>
      </form>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="credential-field">
      <div className="credential-field-label">{label}</div>
      <div className="credential-field-value">{value}</div>
    </div>
  );
}
