// API keys are not account passwords. "new-password" stops browsers from filling a
// saved login into these fields (and offering to save keys as logins); the data-*
// flags do the same for common password-manager extensions.
export const secretInputProps = {
  type: "password",
  autoComplete: "new-password",
  slotProps: {
    htmlInput: {
      "data-lpignore": "true",
      "data-1p-ignore": "true",
      "data-bwignore": "true",
      "data-form-type": "other",
      spellCheck: false,
    },
  },
};
