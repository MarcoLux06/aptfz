.PHONY: test check deb install uninstall clean

VERSION    := $(shell sed -n 's/^__version__ = "\(.*\)"/\1/p' src/lib/config.py)
# Set this to your real name/address when building a release:
#   make deb MAINTAINER='Jane Doe <jane@example.org>'
MAINTAINER ?= Marco Lux <89221170+MarcoLux06@users.noreply.github.com>
DEB        := build/aptfz_$(VERSION)_all.deb
ROOT       := build/root

test:
	python3 -m pytest tests/ -q

check:
	@for f in src/aptfz src/aptq src/key-bindings.bash; do bash -n $$f 2>/dev/null || python3 -m py_compile $$f; done
	@python3 -m compileall -q src/lib && echo "syntax OK"

# Build the .deb into build/. Does not run the test suite (make test).
deb: check
	rm -rf $(ROOT)
	install -d $(ROOT)/DEBIAN $(ROOT)/usr/bin $(ROOT)/usr/share/aptfz/lib \
	  $(ROOT)/usr/share/man/man1 $(ROOT)/usr/share/doc/aptfz
	install -m755 src/aptfz src/aptq $(ROOT)/usr/bin/
	install -m644 src/lib/*.py $(ROOT)/usr/share/aptfz/lib/
	install -m644 src/key-bindings.bash src/key-bindings.zsh $(ROOT)/usr/share/aptfz/
	for m in aptfz aptq; do gzip -9n -c src/man/$$m.1 > $(ROOT)/usr/share/man/man1/$$m.1.gz; done
	chmod 644 $(ROOT)/usr/share/man/man1/*.gz
	install -m644 LICENSE $(ROOT)/usr/share/doc/aptfz/copyright
	install -m644 README.md $(ROOT)/usr/share/doc/aptfz/README.md
	sed -e 's/@MAINTAINER@/$(MAINTAINER)/' -e 's/@DATE@/'"$$(date -R)"'/' \
	  packaging/changelog | gzip -9n > $(ROOT)/usr/share/doc/aptfz/changelog.gz
	chmod 644 $(ROOT)/usr/share/doc/aptfz/changelog.gz
	install -m755 packaging/postinst packaging/prerm $(ROOT)/DEBIAN/
	size=$$(du -sk --exclude=DEBIAN $(ROOT) | cut -f1); \
	sed -e 's/@VERSION@/$(VERSION)/' -e 's/@MAINTAINER@/$(MAINTAINER)/' -e "s/@SIZE@/$$size/" \
	  packaging/control.in > $(ROOT)/DEBIAN/control
	cd $(ROOT) && find usr -type f -exec md5sum {} + > DEBIAN/md5sums
	dpkg-deb --root-owner-group --build $(ROOT) $(DEB)
	@echo "built $(DEB)"

install: deb
	sudo apt install ./$(DEB)

uninstall:
	sudo apt remove aptfz

clean:
	rm -rf build .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
