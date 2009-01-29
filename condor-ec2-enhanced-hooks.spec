%{!?python_sitelib: %define python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}

Summary: Condor EC2 Enhanced hooks
Name: condor-ec2-enhanced-hooks
Version: 1.0
Release: 11%{?dist}
License: ASL 2.0
Group: Applications/System
URL: http://www.redhat.com/mrg
Source0: %{name}-%{version}.tar.gz
BuildRoot: %(mktemp -ud %{_tmppath}/%{name}-%{version}-%{release}-XXXXXX)
BuildArch: noarch
Requires: python >= 2.3
Requires: condor >= 7.2.0-4
Requires: condor-job-hooks-common >= 1.0-4
Requires: condor-ec2-enhanced-hooks-common
Requires: python-boto >= 1.0a
Requires: openssl

%description
The EC2 Enhanced feature allows for near seamless translation of Condor jobs
in the standard universe to condor EC2 jobs in the grid universe.  For all
intents and purposes, the job runs as any standard universe job runs except
on an Amazon EC2 AMI instance.

This package provides Condor job router hooks that will translate a job into
a Condor EC2 job and monitor the state of that job.  This should be installed
on condor nodes that will submitting work and wish to use the EC2 Enhanced
feature.

%package common
Summary: Common functions/utilities for condor job hooks
Group: Applications/System
BuildRequires: python-devel
Requires: python >= 2.3

%description common
Common functions and utilities used by MRG condor job hooks.

%prep
%setup -q

%install
mkdir -p %{buildroot}/%_libexecdir/condor/hooks
mkdir -p %{buildroot}/%{python_sitelib}/ec2enhanced
mkdir -p %{buildroot}/%_sysconfdir/opt/grid
mkdir -p %{_builddir}/%{name}-%{version}/example
cp -f hook*.py %{buildroot}/%_libexecdir/condor/hooks
cp -f functions.py %{buildroot}/%{python_sitelib}/ec2enhanced
cp -f config/condor_config.example %{_builddir}/%{name}-%{version}/example
touch %{buildroot}/%{python_sitelib}/ec2enhanced/__init__.py

%files
%defattr(-,root,root,-)
%doc LICENSE-2.0.txt INSTALL example
%defattr(0755,root,root,-)
%_libexecdir/condor/hooks/hook_job_finalize.py*
%_libexecdir/condor/hooks/hook_translate.py*
%_libexecdir/condor/hooks/hook_cleanup.py*
%_libexecdir/condor/hooks/hook_retrieve_status.py*

%files common
%defattr(-,root,root,-)
%doc LICENSE-2.0.txt
%{python_sitelib}/ec2enhanced/functions.py*
%{python_sitelib}/ec2enhanced/__init__.py*

%changelog
* Tue Jan 20 2009  <rrati@redhat> - 1.0-11
- Fixed problems in the translate hook when a job is rerouted
- Cleaned up classad parsing
- Increment counter denoting number of run attempts in EC2

* Tue Jan 13 2009  <rrati@redhat> - 1.0-10
- Added handling of exceptions when retrieving queues from SQS
- Finalize hook now updates the source job's stats

* Thu Dec 18 2008  <rrati@redhat> - 1.0-9
- Status hook no longer outputs updates if the job completed
- Finalize hook prints ID of job that doesn't run
- Cleanly remove tempory directory on failure cases

* Mon Dec 15 2008  <rrati@redhat> - 1.0-8
- The status hook outputs updates, not entire classads
- The finalize hook does file remapping and places files in job's iwd
- The finalize hook attempts to access AWS multiple times before quitting

* Sat Dec 13 2008  <rrati@redhat> - 1.0-7
- Use GlobalJobId a part of unique S3 key
- Handle more failure conditions when accessing AWS
- Errors are printed to stderr
- Read results from unique queue per job
- Simplication of hooks since queues are now unique
- Clean hook ensures all information has been remove from AWS
- Finalize hook failure will force job to be re-routed
- Translate hook now uses AmazonUserData instead of AmazonUserDataFile

* Tue Dec  9 2008  <rrati@redhat> - 1.0-6
- S3 data is stored in unique buckets
- Print errors when having problems accessing S3
- Only encrypted the AWS secret access key and base64 encode
- Print error message if invalid key files are given
- Handle bad messages in SQS queues

* Sun Dec  7 2008  <rrati@redhat> - 1.0-5
- Fixed python dep issue on RHEL4
- Changes for python 2.3 compatibility
- Added openssl dependency

* Mon Dec  1 2008  <rrati@redhat> - 1.0-4
- Fixed issue with uppercase file names being converted to lowercase names
  (BZ474071)

* Fri Nov  4 2008  <rrati@redhat> - 1.0-3
- Removed INSTALL and example from the common package
- Updated INSTALL to mention RSA Private Key file

* Fri Nov  4 2008  <rrati@redhat> - 1.0-2
- Add changelog
- Fix rpmlint issues

* Fri Nov  4 2008  <rrati@redhat> - 1.0-1
- Initial packaging
