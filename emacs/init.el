;; -*- lexical-binding: t; -*-

;;; Bootstrap straight.el
(setq-default straight-repository-branch "develop")
(defvar bootstrap-version)
(let ((bootstrap-file
       (expand-file-name "straight/repos/straight.el/bootstrap.el" user-emacs-directory))
      (bootstrap-version 6))
  (unless (file-exists-p bootstrap-file)
    (with-current-buffer
        (url-retrieve-synchronously
         "https://raw.githubusercontent.com/radian-software/straight.el/develop/install.el"
         'silent 'inhibit-cookies)
      (goto-char (point-max))
      (eval-print-last-sexp)))
  (load bootstrap-file nil 'nomessage))

(setq straight-use-package-by-default t
      straight-vc-git-default-clone-depth 1)

(straight-use-package '(use-package :type built-in))

;;; Core utilities
(use-package no-littering
  :demand t
  :config
  (setq custom-file (no-littering-expand-etc-file-name "custom.el")))

;; Better GC strategy at runtime
(use-package gcmh
  :demand t
  :config
  (gcmh-mode))

;; Inherit PATH and env from shell
(use-package exec-path-from-shell
  :config
  (exec-path-from-shell-initialize))

;; Show available keybindings in a popup
(use-package which-key
  :config
  (which-key-mode))

;;; Misc built-in settings
(show-paren-mode t)
(column-number-mode t)
(global-subword-mode t)
(pixel-scroll-precision-mode t)

(setq project-switch-commands 'project-find-file)

;;; Start server for emacsclient
(use-package server
  :straight (:type built-in)
  :config
  (setq server-socket-dir (expand-file-name "server" user-emacs-directory))
  (unless (server-running-p)
    (server-start)))

;;; Modules
(require 'init-ui)
(require 'init-evil)
(require 'init-git)
(require 'init-nav)
(require 'init-keys)

(provide 'init)
