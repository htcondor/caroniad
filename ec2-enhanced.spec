Summary: EC2 Enhanced
Name: ec2-enhanced
Version: 1.0
Release: 1%{?dist}
License: ASL 2.0
Group: Applications/System
Source0: %{name}-%{version}.tar.gz
BuildRoot: %(mktemp -ud %{_tmppath}/%{name}-%{version}-%{release}-XXXXXX)
BuildArch: noarch
Requires: python >= 2.4
Requires: condor >= 7.0.2-4
Requires: condor-job-hooks
Requires: condor-job-hooks-common
Requires: ec2-enhanced-hooks-common
Requires: python-boto >= 1.0a

Requires(post):/sbin/chkconfig
Requires(preun):/sbin/chkconfig
Requires(preun):/sbin/service
Requires(postun):/sbin/service

%description
The EC2 Enhanced feature allows for near seamless translation of Condor jobs
in the standard universe to condor EC2 jobs in the grid universe.  For all
intents and purposes, the job runs as any standard universe job runs except
on an Amazon EC2 AMI instance.

This package contains the daemon that handles the communication between
Condor and the Amazon Web Services (AWS).  This should be installed on an
Amazon Machine Instance (AMI) that will be used with Condor's EC2 Enhanced
feature.

%prep
%setup -q

%install
mkdir -p %{buildroot}%{_sbindir}
mkdir -p %{buildroot}/%{_sysconfdir}/opt/grid
mkdir -p %{buildroot}/%{_initrddir}
cp -f caroniad %{buildroot}/%_sbindir
cp -f config/caroniad.conf %{buildroot}/%{_sysconfdir}/opt/grid
cp -f config/caronia.init %{buildroot}/%{_initrddir}/caronia

%post
/sbin/chkconfig --add caronia

%preun
if [ $1 = 0 ]; then
  /sbin/service caronia stop >/dev/null 2>&1 || :
  /sbin/chkconfig --del caronia
fi

%postun
if [ "$1" -ge "1" ]; then
  /sbin/service caronia condrestart >/dev/null 2>&1 || :
fi

%files
%defattr(-,root,root,-)
%doc LICENSE-2.0.txt
%config(noreplace) %_sysconfdir/opt/grid/caroniad.conf
%attr(0755,root,root) %_initrddir/caronia
%defattr(0555,root,root,-)
%_sbindir/caroniad
