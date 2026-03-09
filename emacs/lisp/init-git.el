;; -*- lexical-binding: t; -*-

;;; Magit — the main reason this config exists
(use-package magit
  :custom
  (magit-diff-highlight-hunk-region-functions
   '(magit-diff-highlight-hunk-region-dim-outside
     magit-diff-highlight-hunk-region-using-face))
  :custom-face
  (magit-diff-hunk-region ((t (:slant italic)))))

;;; Gutter indicators for added/changed/deleted lines
(use-package diff-hl
  :custom
  (diff-hl-margin-symbols-alist '((insert  . " ")
                                  (delete  . " ")
                                  (change  . " ")
                                  (unknown . " ")
                                  (ignored . " ")))
  :config
  (add-hook 'magit-post-refresh-hook 'diff-hl-magit-post-refresh)
  (global-diff-hl-mode))

;;; Show commit message for the line at point
(use-package vc-msg)

;;; Step through a file's git history
(use-package git-timemachine
  :defer t
  :config
  (with-eval-after-load 'evil
    (evil-make-overriding-map git-timemachine-mode-map 'normal)
    (add-hook 'git-timemachine-mode-hook #'evil-normalize-keymaps)))


(provide 'init-git)
