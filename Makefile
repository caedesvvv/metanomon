DESTDIR=/usr
all:

install:
	install -m 755 -d $(DESTDIR)/share/python-support/metanomon/metanomon
	install -m 755 -d $(DESTDIR)/share/metanomon/
	install -m 755 -d $(DESTDIR)/share/metanomon/metanomon/
	install -m 755 -d $(DESTDIR)/share/metanomon/images/
	install -m 755 -d $(DESTDIR)/share/metanomon/glade/
	install -m 755 -d $(DESTDIR)/bin/
	install -m 755 bin/* $(DESTDIR)/bin
	install -m 755 metanomon/*.py $(DESTDIR)/share/python-support/metanomon/metanomon
	install -m 755 images/* $(DESTDIR)/share/metanomon/images/
	install -m 755 glade/*.glade $(DESTDIR)/share/metanomon/glade/
