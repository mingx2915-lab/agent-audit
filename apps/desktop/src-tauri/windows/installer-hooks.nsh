!macro NSIS_HOOK_POSTUNINSTALL
  ; The stock Tauri template only removes the product install-location key
  ; when the optional app-data deletion checkbox is selected. Always remove
  ; this installer-owned key after uninstall, while preserving all user data.
  DeleteRegKey SHCTX "${MANUPRODUCTKEY}"
  DeleteRegKey /ifempty SHCTX "${MANUKEY}"
!macroend
