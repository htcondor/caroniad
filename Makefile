.PHONY: build condor-ec2-enhanced condor-ec2-enhanced-hooks

RPMBUILD_DIRS := BUILD BUILDROOT RPMS SOURCES SPECS SRPMS BUILDROOT

NAME := condor-ec2-enhanced
EC2E_SPEC := ${NAME}.spec
EC2E_VERSION := $(shell grep -i version: "${EC2E_SPEC}" | awk '{print $$2}')
EC2E_SOURCE := ${NAME}-${EC2E_VERSION}.tar.gz
EC2E_DIR := ${NAME}-${EC2E_VERSION}
NAME := condor-ec2-enhanced-hooks
EC2EHOOKS_SPEC := ${NAME}.spec
EC2EHOOKS_VERSION := $(shell grep -i version: "${EC2EHOOKS_SPEC}" | awk '{print $$2}')
EC2EHOOKS_SOURCE := ${NAME}-${EC2EHOOKS_VERSION}.tar.gz
EC2EHOOKS_DIR := ${NAME}-${EC2EHOOKS_VERSION}

build: condor-ec2-enhanced condor-ec2-enhanced-hooks

condor-ec2-enhanced: SPECS/${EC2E_SPEC} SOURCES/${EC2E_SOURCE}
	mkdir -p BUILD RPMS SRPMS
	rpmbuild --define="_topdir ${PWD}" -ba SPECS/${EC2E_SPEC}

condor-ec2-enhanced-hooks: SPECS/${EC2EHOOKS_SPEC} SOURCES/${EC2EHOOKS_SOURCE}
	mkdir -p BUILD RPMS SRPMS
	rpmbuild --define="_topdir ${PWD}" -ba SPECS/${EC2EHOOKS_SPEC}

SPECS/${EC2E_SPEC}: ${EC2E_SPEC}
	mkdir -p SPECS
	cp -f ${EC2E_SPEC} SPECS

SPECS/${EC2EHOOKS_SPEC}: ${EC2EHOOKS_SPEC}
	mkdir -p SPECS
	cp -f ${EC2EHOOKS_SPEC} SPECS

SOURCES/${EC2EHOOKS_SOURCE}: hooks/sqs.py hooks/region.py \
                         hooks/hook_cleanup.py hooks/hook_job_finalize.py \
                         hooks/hook_retrieve_status.py hooks/hook_translate.py \
                         config/60condor-ec2e-hooks.config.example
	mkdir -p SOURCES
	rm -rf ${EC2EHOOKS_DIR}
	mkdir ${EC2EHOOKS_DIR}
	mkdir ${EC2EHOOKS_DIR}/config
	cp -f hooks/* ${EC2EHOOKS_DIR}
	cp -f LICENSE-2.0.txt ${EC2EHOOKS_DIR}
	cp -f INSTALL.hooks ${EC2EHOOKS_DIR}/INSTALL
	cp -f config/60condor-ec2e-hooks.config.example ${EC2EHOOKS_DIR}/config
	tar -zcf ${EC2EHOOKS_SOURCE} ${EC2EHOOKS_DIR}
	mv "${EC2EHOOKS_SOURCE}" SOURCES

SOURCES/${EC2E_SOURCE}: caroniad config/60condor-ec2e.config
	mkdir -p SOURCES
	rm -rf ${EC2E_DIR}
	mkdir ${EC2E_DIR}
	mkdir ${EC2E_DIR}/config
	cp -f caroniad ${EC2E_DIR}
	cp -f LICENSE-2.0.txt INSTALL ${EC2E_DIR}
	cp -f config/60condor-ec2e.config ${EC2E_DIR}/config
	tar -zcf ${EC2E_SOURCE} ${EC2E_DIR}
	mv "${EC2E_SOURCE}" SOURCES

clean:
	rm -rf ${RPMBUILD_DIRS} ${EC2E_DIR} ${EC2EHOOKS_DIR}
