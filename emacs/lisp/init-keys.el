;; -*- lexical-binding: t; -*-

(defun my/open-in-vscode ()
  "Open the current file in VSCode at the current line."
  (interactive)
  (let ((file (buffer-file-name))
        (line (line-number-at-pos)))
    (if file
        (start-process "vscode" nil "code" "--goto" (format "%s:%d" file line))
      (message "Buffer is not visiting a file"))))

(use-package general
  :config
  (general-evil-setup)

  ;; Global bindings
  (general-define-key
   :keymaps 'global

   ;; Disable accidental scroll zoom
   "C-<wheel-up>"    'ignore
   "C-<wheel-down>"  'ignore

   ;; Search
   "<f1>" 'counsel-rg          ; ripgrep in project
   "<f2>" 'counsel-git         ; find file in git repo

   ;; File tree
   "<f3>" 'treemacs-select-window

   ;; Open current file in VSCode at current line
   "C-<f12>" 'my/open-in-vscode)

  ;; SPC leader (normal + visual + emacs states)
  (general-create-definer my/leader-keys
    :states '(normal visual emacs)
    :keymaps 'override
    :prefix "SPC"
    :global-prefix "C-SPC")

  (my/leader-keys
    "SPC" '(counsel-M-x :which-key "M-x")
    "/"   '(my/swiper-thing-at-point :which-key "Swiper at point")
    "?"   '(my/counsel-rg-at-point :which-key "Search in project at point")
    "TAB" '(my/switch-to-previous-buffer :which-key "Previous buffer")

    ;; Buffer
    "b"   '(:ignore t :which-key "Buffer")
    "b b" '(ivy-switch-buffer :which-key "Switch")
    "b k" '(kill-buffer :which-key "Kill")
    "b n" '(next-buffer :which-key "Next")
    "b p" '(previous-buffer :which-key "Previous")

    ;; File
    "f"   '(:ignore t :which-key "File")
    "f f" '(counsel-find-file :which-key "Find file")
    "f r" '(counsel-recentf :which-key "Recent files")
    "f s" '(save-buffer :which-key "Save")
    ";"   '(save-buffer :which-key "Save file")

    ;; Git
    "g"   '(:ignore t :which-key "Git")
    "g b" '(magit-blame :which-key "Blame")
    "g m" '(vc-msg-show :which-key "Commit message")
    "g s" '(magit-status :which-key "Status")
    "g t" '(git-timemachine :which-key "Time machine")
    "v"   '(magit-status :which-key "Magit status")

    ;; Help
    "h"   '(:ignore t :which-key "Help")
    "h f" '(counsel-describe-function :which-key "Function")
    "h k" '(describe-key :which-key "Key")
    "h v" '(counsel-describe-variable :which-key "Variable")

    ;; Jump (avy)
    "j"   '(:ignore t :which-key "Jump")
    "j c" '(avy-goto-char-timer :which-key "Char timer")
    "j e" '(avy-goto-end-of-line :which-key "End of line")
    "j l" '(avy-goto-char-in-line :which-key "Char in line")
    "j w" '(avy-goto-word-1 :which-key "Word")

    ;; Toggle
    "t"   '(:ignore t :which-key "Toggle")
    "t l" '(display-line-numbers-mode :which-key "Line numbers")
    "t t" '(toggle-truncate-lines :which-key "Truncate lines")

    ;; Window
    "w"   '(:ignore t :which-key "Window")
    "w =" '(balance-windows :which-key "Balance")
    "w b" '(evil-window-left :which-key "Left")
    "w d" '(delete-window :which-key "Delete")
    "w f" '(evil-window-right :which-key "Right")
    "w h" '(my/split-window-below :which-key "Split horizontal")
    "w n" '(evil-window-down :which-key "Down")
    "w o" '(delete-other-windows :which-key "Delete others")
    "w p" '(evil-window-up :which-key "Up")
    "w v" '(my/split-window-right :which-key "Split vertical"))

  ;; Evil normal state
  (general-define-key
   :states 'normal
   "s" 'avy-goto-char-2
   "u" 'undo-fu-only-undo
   "U" 'undo-fu-only-redo
   "/" 'swiper)

  ;; Evil visual state
  (general-define-key
   :states 'visual
   "=" 'align-regexp)

  ;; Package-specific maps
  (general-define-key
   :keymaps 'ivy-minibuffer-map
   "TAB" 'ivy-partial
   "RET" 'ivy-alt-done)

  (general-define-key
   :keymaps 'evil-emacs-state-map
   "<escape>" 'evil-exit-emacs-state)

  (general-define-key
   :keymaps 'treemacs-mode-map
   "<f3>" 'treemacs-select-window))


(provide 'init-keys)
