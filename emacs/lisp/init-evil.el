;; -*- lexical-binding: t; -*-

;;; Line numbers (relative — useful for evil motion counts)
(setq display-line-numbers-type 'relative)
(add-hook 'prog-mode-hook (lambda () (display-line-numbers-mode t)))

;;; Undo system (required by evil)
(use-package undo-fu)

;;; Evil mode
(use-package evil
  :init
  (setq evil-want-keybinding      nil
        evil-undo-system          'undo-fu
        evil-emacs-state-cursor   'bar
        evil-visual-state-cursor  'hollow)
  :config
  (evil-mode)
  (evil-set-leader 'normal (kbd "SPC"))
  ;; Use emacs state instead of insert/motion — keeps Emacs bindings in those contexts
  (defalias 'evil-insert-state 'evil-emacs-state)
  (defalias 'evil-motion-state 'evil-emacs-state)
  ;; Use emacs state in git commit buffers
  (with-eval-after-load 'git-commit
    (add-hook 'git-commit-mode-hook #'evil-emacs-state)))

;; Integrates evil with many built-in and popular packages
(use-package evil-collection
  :after evil
  :config
  (evil-collection-init))

;; Visual feedback when yanking, deleting, etc.
(use-package evil-goggles
  :after evil
  :custom
  (evil-goggles-enable-change nil)
  (evil-goggles-enable-delete nil)
  :config
  (evil-goggles-mode))

;; Extends % matching to HTML tags, if/end blocks, etc.
(use-package evil-matchit
  :after evil
  :config
  (global-evil-matchit-mode))

;; Press key sequence quickly to escape to normal state
(use-package evil-escape
  :after evil
  :custom
  (evil-escape-delay 0.15)
  (evil-escape-key-sequence "uh")
  :config
  (evil-escape-mode))

;; Surround text objects with pairs (ys, cs, ds)
(use-package evil-surround
  :after evil
  :config
  (global-evil-surround-mode))

;; Quick comment toggling
(use-package evil-nerd-commenter
  :after evil
  :config
  (evilnc-default-hotkeys))


(provide 'init-evil)
