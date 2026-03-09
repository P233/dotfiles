;; -*- lexical-binding: t; -*-

;;; Ivy / Counsel — fuzzy completion for files, buffers, search
(use-package counsel
  :demand t
  :custom
  (ivy-wrap t)
  (ivy-height 20)
  (ivy-use-virtual-buffers t)
  (ivy-use-selectable-prompt t)
  (enable-recursive-minibuffers t)
  (counsel-find-file-ignore-regexp
   (regexp-opt '(".git" ".dist" ".next" ".husky" ".DS_Store" "node_modules")))
  :config
  (defun my/swiper-thing-at-point ()
    "Search for symbol at point with swiper."
    (interactive)
    (swiper (thing-at-point 'symbol)))
  (defun my/counsel-rg-at-point ()
    "Run ripgrep in project root with symbol at point pre-filled."
    (interactive)
    (let* ((symbol (thing-at-point 'symbol))
           (search-term (if symbol (regexp-quote symbol) ""))
           (project-root (or (project-root (project-current))
                             (vc-root-dir))))
      (counsel-rg search-term project-root)))
  (setq ivy-switch-buffer-faces-alist '((dired-mode . ivy-subdir)))
  (ivy-mode t))

;; Smarter sorting for ivy candidates
(use-package prescient
  :config
  (prescient-persist-mode))

(use-package ivy-prescient
  :custom
  (ivy-prescient-enable-filtering nil)
  (ivy-prescient-retain-classic-highlighting t)
  :config
  (ivy-prescient-mode))

;; Show xref results (definitions, references) in ivy
(use-package ivy-xref
  :custom
  (xref-show-xrefs-function #'ivy-xref-show-defs)
  (xref-show-definitions-function #'ivy-xref-show-defs))

;;; Avy — jump to any visible text with a few keystrokes
(use-package avy
  :custom
  (avy-keys '(?o ?e ?u ?h ?l ?r ?p ?a ?s ?d ?f ?g ?j ?k ?c ?v ?b ?w ?q))
  (avy-styles-alist '((avy-goto-char . de-bruijn))))

;;; Editable grep results (handy after counsel-rg)
(use-package wgrep
  :defer t)

;;; Useful buffer switch helper
(defun my/switch-to-previous-buffer ()
  "Toggle between the two most recently visited buffers."
  (interactive)
  (switch-to-buffer (other-buffer (current-buffer) 1)))


(provide 'init-nav)
