%{!?python_sitelib: %define python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}

Summary: HTCondor EC2 Enhanced hooks
Name: condor-ec2-enhanced-hooks
Version: 1.3.1
Release: 1%{?dist}
License: ASL 2.0
Group: Applications/System
URL: http://git.fedorahosted.org/git/grid/caroniad.git
Source0: %{name}-%{version}.tar.gz
BuildRoot: %(mktemp -ud %{_tmppath}/%{name}-%{version}-%{release}-XXXXXX)
BuildArch: noarch
Requires: python >= 2.3
Requires: condor >= 7.2.0-4
Requires: python-condorutils >= 1.5
Requires: python-condorec2e = %{version}
Requires: python-boto >= 1.7a
Requires: openssl

%description
The EC2 Enhanced feature allows for near seamless translation of HTCondor jobs
in the vanilla universe to HTCondor EC2 jobs in the grid universe.  For all
intents and purposes, the job runs as any vanilla universe job runs except
on an Amazon EC2 AMI instance.

This package provides HTCondor job router hooks that will translate a job into
a HTCondor EC2 job and monitor the state of that job.  This should be installed
on HTCondor nodes that will submitting work and wish to use the EC2 Enhanced
feature.

%package -n python-condorec2e
Summary: Common definitions for EC2 Enhanced
Group: Applications/System
BuildRequires: python-devel
Requires: python >= 2.3
Obsoletes: condor-ec2-enhanced-hooks-common
Obsoletes: python-condor-ec2-enhanced-hooks-common

%description -n python-condorec2e
Common definitions used by HTCondor's EC2 Enhanced functionality

%prep
%setup -q

%build

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}/%_libexecdir/condor/hooks
mkdir -p %{buildroot}/%{python_sitelib}/condorec2e
mkdir -p %{_builddir}/%{name}-%{version}/example
cp -f hook*.py %{buildroot}/%_libexecdir/condor/hooks
cp -f sqs.py %{buildroot}/%{python_sitelib}/condorec2e
cp -f region.py %{buildroot}/%{python_sitelib}/condorec2e
cp -f config/60condor-ec2e-hooks.config.example %{_builddir}/%{name}-%{version}/example
touch %{buildroot}/%{python_sitelib}/condorec2e/__init__.py

%clean
rm -rf %{buildroot}

%files
%defattr(-,root,root,-)
%doc LICENSE-2.0.txt INSTALL example
%defattr(0755,root,root,-)
%_libexecdir/condor/hooks/hook_job_finalize.py*
%_libexecdir/condor/hooks/hook_translate.py*
%_libexecdir/condor/hooks/hook_cleanup.py*
%_libexecdir/condor/hooks/hook_retrieve_status.py*

%files -n python-condorec2e
%defattr(-,root,root,-)
%doc LICENSE-2.0.txt
%{python_sitelib}/condorec2e/__init__.py*
%{python_sitelib}/condorec2e/sqs.py*
%{python_sitelib}/condorec2e/region.py*

%changelog
* Thu Apr 5 2012  <rrati@redhat> - 1.3.1-1
- Added additional parameters that give insight into job status in
  the AMI (BZ738335)

* Thu Dec 8 2011  <rrati@redhat> - 1.3.0-1
- Added support for aws region

* Mon Aug 29 2011  <rrati@redhat> - 1.2-4
- Raise exception if the translate hook is unable to read important files

* Wed Jun 29 2011  <rrati@redhat> - 1.2-3
- Updated docs
- Changed example config file to be easily dropped into /etc/condor/config.d
- Set WantAWS = False in classad sent to the EC2 AMI

* Wed May 18 2011  <rrati@redhat> - 1.2-2
- Fixed issues using 64-bit AMIs

* Wed Apr 27 2011  <rrati@redhat> - 1.2-1
- Fixed compatibility with ec2_gahp
- Enhanced check for the ec2_gahp binary
- Fixed issue with HookKeyword getting updated in original job and preventing
  cleanup hook from running
- Updated dep on python-condorec2e to match hooks package version

* Thu Mar 17 2011  <rrati@redhat> - 1.1-3
- Removed the setting of the GridResource in the example routes
- Updated the job finalize hook to work with newer versions of python
- Added dep on python-condorutils >= 1.5

* Mon Jan  3 2011  <rrati@redhat> - 1.1-2
- Updated source URL
- Remove mention of EC2E_HOOK params from the example config file

* Mon Jun 28 2010  <rrati@redhat> - 1.1-1
- Added versions on deps for python-ec2e and python-condorutils
- Fixed description (standard -> vanilla)
- Typo fixes

* Fri Jun 11 2010  <rrati@redhat> - 1.1-0.2
- Logging is to stderr only

* Tue Mar 30 2010  <rrati@redhat> - 1.1-0.1
- Updated INSTALL docs
- Changed to using condorutils and condorec2e modules
- Use log logging call install of syslog
- Added 2 params for controlling log files
- Renamed functions module to sqs

* Tue Aug 18 2009  <rrati@redhat> - 1.0-19
- Split the documentation into two files, one for the AMI and one for
  the submit machine
- Fixed obsolete issue with common package
- SQS/S3 queues/buckets no longer use GlobalJobId because they can be too
  long for AWS.  Instead, ClusterId, ProcId, and QDate is used.

* Mon Jul 27 2009  <rrati@redhat> - 1.0-18
- Fixed dependency issue

* Mon Jul 27 2009  <rrati@redhat> - 1.0-17
- Fixed missed dependency renames

* Mon Jul 27 2009  <rrati@redhat> - 1.0-16
- Renamed condor-ec2-enhanced-hooks-common to
  python-condor-ec2-enhanced-hooks to conform to packaging guidelines
  since the package installs in python sitelib.

* Mon Jul 27 2009  <rrati@redhat> - 1.0-15
- Fixed rpmlint/packaging issues

* Fri Feb 27 2009  <rrati@redhat> - 1.0-14
- Update docs
- Changes to work with boto 1.7a

* Fri Feb 13 2009  <rrati@redhat> - 1.0-13
- Rebuild bump

* Fri Feb 13 2009  <rrati@redhat> - 1.0-12
- Change tarball name

* Tue Feb  5 2009  <rrati@redhat> - 1.0-11
- Fixed problems in the translate hook when a job is rerouted
- Cleaned up classad parsing
- Increment counter denoting number of run attempts in EC2
- Fixed logic error if the S3 key wasn't created by the translate hook
- Changed Cmd attribute for routed job to be: "EC2: <route name>: <original cmd>"

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
