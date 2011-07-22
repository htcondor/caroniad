%{!?is_fedora: %define is_fedora %(/bin/sh -c "if [ -e /etc/fedora-release ];then echo '1'; fi")}
%define rel 2

Summary: EC2 Enhanced
Name: condor-ec2-enhanced
Version: 1.2
Release: %{rel}%{?dist}
License: ASL 2.0
Group: Applications/System
URL: http://git.fedorahosted.org/git/grid/caroniad.git
Source0: %{name}-%{version}-%{rel}.tar.gz
BuildRoot: %(mktemp -ud %{_tmppath}/%{name}-%{version}-%{release}-XXXXXX)
BuildArch: noarch
Requires: python >= 2.4
Requires: condor >= 7.4.4-0.9
Requires: condor-job-hooks
Requires: python-condorutils >= 1.5-4
Requires: python-condorec2e >= 1.1
Requires: python-boto >= 1.7a
Requires: openssl

%description
The EC2 Enhanced feature allows for near seamless translation of Condor jobs
in the vanilla universe to condor EC2 jobs in the grid universe.  For all
intents and purposes, the job runs as any vanilla universe job runs except
on an Amazon EC2 AMI instance.

This package contains the daemon that handles the communication between
Condor and the Amazon Web Services (AWS).  This should be installed on an
Amazon Machine Instance (AMI) that will be used with Condor's EC2 Enhanced
feature.

%prep
%setup -q

%build

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}%{_sbindir}
mkdir -p %{buildroot}/%_sysconfdir/condor/config.d
cp -f caroniad %{buildroot}/%_sbindir
cp -f config/60condor-ec2e.config %{buildroot}/%_sysconfdir/condor/config.d

%clean
rm -rf %{buildroot}

%post
%if 0%{?is_fedora} == 0
if [[ -f /etc/opt/grid/caroniad.conf ]]; then
   mv -f /etc/opt/grid/caroniad.conf /etc/condor
   rmdir --ignore-fail-on-non-empty -p /etc/opt/grid
fi
%endif
exit 0

%files
%defattr(-,root,root,-)
%doc LICENSE-2.0.txt INSTALL
%_sysconfdir/condor/config.d/60condor-ec2e.config
%defattr(0755,root,root,-)
%_sbindir/caroniad

%changelog
* Fri Jul 22 2011  <rrati@redhat> - 1.2-2
- Updated dep on python-condorutils
- Added missing config params to config file

* Wed Jun 29 2011  <rrati@redhat> - 1.2-1
- Install config file into /etc/condor/config.d
- Changed daemon name in config to CARONIAD, old name still supported
- Updated docs

* Mon Feb  8 2011  <rrati@redhat> - 1.1-3
- Updated dep on python-condorutils

* Mon Jan  3 2011  <rrati@redhat> - 1.1-2
- Updated source URL

* Mon Jun 28 2010  <rrati@redhat> - 1.1-1
- Added versions on deps for python-ec2e and python-condorutils
- Fixed description (standard -> vanilla)

* Fri Jun 11 2010  <rrati@redhat> - 1.1-0.2
- Additional logging
- Additional signal handling

* Tue Mar 30 2010  <rrati@redhat> - 1.1-0.1
- Updated INSTALL docs
- Changed to using condorutils and condorec2e modules
- Use log logging call install of syslog
- Renamed exceptions and define locally instead of relying on definition
  in condorutils
- Code cleanup
- Added 2 params for controlling log files

* Fri Oct 23 2009  <rrati@redhat> - 1.0-18
- Removed conflict with condor-low-latency

* Tue Aug 18 2009  <rrati@redhat> - 1.0-17
- caroniad checks condor_config for its configuration before looking
  in configuration files
- Removed the init script as the daemon is controlled by condor now
- Split the documentation into two files, one for the AMI and one for
  the submit machine
- Added conflict with condor-low-latency

* Mon Jul 27 2009  <rrati@redhat> - 1.0-16
- Fixed missed dependency renames

* Mon Jul 27 2009  <rrati@redhat> - 1.0-15
- Updated dependencies to match hooks-common rename

* Mon Jul 27 2009  <rrati@redhat> - 1.0-14
- Fixed rpmlint/packaging issues

* Wed Jul 22 2009  <rrati@redhat> - 1.0-13
- Added Fedora packaging support

* Wed Jul 22 2009  <rrati@redhat> - 1.0-12
- Moved configuration files to /etc/condor

* Tue Jun  2 2009  <rrati@redhat> - 1.0-11
- Remove RLocks and added better error handling to reduce deadlock potential
- Changes to work with boto 1.7a

* Fri Feb 13 2009  <rrati@redhat> - 1.0-10
- Rebuild bump

* Fri Feb 13 2009  <rrati@redhat> - 1.0-9
- Change source tarball name

* Thu Jan 22 2009  <rrati@redhat> - 1.0-8
- Every time a job is run, a status message denoting a run attempt
  is put in SQS (BZ480841)
- When processing a job, any attributes added by caroniad will be
  removed first to ensure no duplicates
- Fixed issue transfering results to S3 if the job had no data sent

* Mon Dec 15 2008  <rrati@redhat> - 1.0-7
- Daemon no longer returns files created outside the job's iwd
- Upon exit, reset visibility timeout for jobs that haven't finished
- Attempt to access AWS multiple times before shutting down the AMI
- Only package files in the job's iwd
- If TransferOutput is set, only transfer the files listed as well as
  stdout/stderr files if they exist

* Sat Dec 13 2008  <rrati@redhat> - 1.0-6
- Use GlobalJobId as part of unique S3 key
- Each job gets unique results and request queues
- AMI will shutdown if it has problems accessing AWS on startup
- Gracefully handle AWS access issues
- Look for shutdown timer in job ad, and if it exists wait to shutdown

* Tue Dec  9 2008  <rrati@redhat> - 1.0-5
- Fixed JobStatus and Owner reporting issues
- AMI is now shutdown after exit message sent
- Only decrypt the AWS secret access key and then base64 decode
- AMI will only wait 15 minutes for a valid message from SQS
- Handle invalid messages in the work queue

* Sun Dec  7 2008  <rrati@redhat> - 1.0-4
- Ensure only 1 job is handled to completion then shutdown
- Added openssl dependency

* Wed Nov 10 2008  <rrati@redhat> - 1.0-3
- Daemon is on by default

* Fri Nov  4 2008  <rrati@redhat> - 1.0-2
- Add changelog
- Fix rpmlint issues
- Changed init script to condor-ec2-enhanced

* Fri Nov  4 2008  <rrati@redhat> - 1.0-1
- Initial packaging
