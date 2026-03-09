;; -*- lexical-binding: t; -*-

;;; Font
(add-to-list 'default-frame-alist '(font . "PragmataPro Mono 18"))
(set-fontset-font "fontset-default" 'han "Noto Serif SC Medium")

;;; Theme
(use-package ef-themes
  :config
  (ef-themes-load-theme 'ef-summer))

;;; Modeline
(use-package doom-modeline
  :custom
  (doom-modeline-icon nil)
  (doom-modeline-height 24)
  (doom-modeline-minor-modes t)
  (doom-modeline-buffer-file-name-style 'truncate-with-project)
  :hook
  (after-init . doom-modeline-mode))

;; Collapse minor modes into a menu in the modeline
;; Default lighter ☰ (U+2630) renders poorly in PragmataPro Mono — use ASCII instead
(use-package minions
  :after doom-modeline
  :custom
  (minions-mode-line-lighter "[+]")
  :config
  (minions-mode t))

;;; File tree (useful for browsing codebases)
(use-package treemacs
  :custom
  (treemacs-width 32)
  (treemacs-text-scale nil)
  (treemacs-no-png-images t)
  (treemacs-show-hidden-files nil)
  (treemacs-file-event-delay 1000)
  (treemacs-position 'right)
  :custom-face
  (treemacs-root-face ((t (:height 1.0 :weight bold))))
  :init
  (defun my/treemacs-ignore-files (_ absolute-path)
    (string-match-p "\\(cache\\|dist\\|node_modules\\)$" absolute-path))
  :config
  (treemacs-project-follow-mode t)
  (setq treemacs--project-follow-delay 0.2)
  (add-to-list 'treemacs-ignored-file-predicates #'my/treemacs-ignore-files)
  :hook
  (treemacs-mode . (lambda () (setq mode-line-format nil))))

(use-package treemacs-evil
  :after (treemacs evil))

;;; Window management
(windmove-default-keybindings)

(defun my/split-window-below ()
  "Split window and switch to the new one with a different buffer."
  (interactive)
  (select-window (split-window-below))
  (switch-to-buffer (other-buffer)))

(defun my/split-window-right ()
  "Split window and switch to the new one with a different buffer."
  (interactive)
  (select-window (split-window-right))
  (switch-to-buffer (other-buffer)))


(provide 'init-ui)
