%define rel 10

Summary: EC2 Enhanced
Name: condor-ec2-enhanced
Version: 1.0
Release: %{rel}%{?dist}
License: ASL 2.0
Group: Applications/System
URL: http://www.redhat.com/mrg
Source0: %{name}-%{version}-%{rel}.tar.gz
BuildRoot: %(mktemp -ud %{_tmppath}/%{name}-%{version}-%{release}-XXXXXX)
BuildArch: noarch
Requires: python >= 2.4
Requires: condor >= 7.0.2-4
Requires: condor-job-hooks
Requires: condor-job-hooks-common
Requires: condor-ec2-enhanced-hooks-common
Requires: python-boto >= 1.0a
Requires: openssl

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
cp -f config/condor-ec2-enhanced.init %{buildroot}/%{_initrddir}/condor-ec2-enhanced

%post
/sbin/chkconfig --add condor-ec2-enhanced

%preun
if [ $1 = 0 ]; then
  /sbin/service condor-ec2-enhanced stop >/dev/null 2>&1 || :
  /sbin/chkconfig --del condor-ec2-enhanced
fi

%postun
if [ "$1" -ge "1" ]; then
  /sbin/service condor-ec2-enhanced condrestart >/dev/null 2>&1 || :
fi

%files
%defattr(-,root,root,-)
%doc LICENSE-2.0.txt
%config(noreplace) %_sysconfdir/opt/grid/caroniad.conf
%defattr(0755,root,root,-)
%_initrddir/condor-ec2-enhanced
%_sbindir/caroniad

%changelog
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
